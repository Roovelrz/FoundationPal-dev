"""Deterministic text and PDF ingestion for RAG evidence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from io import BytesIO

import requests
import yaml
from django.db import transaction

from .embedding_service import EmbeddingService, embed_texts
from .models import AIChunk, AIResource

PARSER_VERSION = 'pdfminer-v1'
TARGET_CHARS = 700
MAX_CHARS = 1000
OVERLAP_CHARS = 100


class IngestionError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    text: str


def _normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def _clean_html(html: str) -> str:
    return _normalize_text(re.sub(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', ' ', html, flags=re.I | re.S))[:200000]


def _chunk_text(text: str, *, target_chars: int = TARGET_CHARS, max_chars: int = MAX_CHARS, overlap_chars: int = OVERLAP_CHARS) -> list[str]:
    units = [unit.strip() for unit in re.split(r'\n+|(?<=[。！？.!?])\s*', text) if unit.strip()]
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for unit in units:
        if len(unit) > max_chars:
            if buffer:
                chunks.append(' '.join(buffer))
                buffer, size = [], 0
            chunks.append(unit)
            continue
        if buffer and size + len(unit) + 1 > max_chars:
            completed = ' '.join(buffer)
            chunks.append(completed)
            overlap = completed[-overlap_chars:].strip()
            buffer, size = ([overlap] if overlap else []), len(overlap)
        buffer.append(unit)
        size += len(unit) + 1
        if size >= target_chars:
            completed = ' '.join(buffer)
            chunks.append(completed)
            overlap = completed[-overlap_chars:].strip()
            buffer, size = ([overlap] if overlap else []), len(overlap)
    if buffer:
        candidate = ' '.join(buffer)
        if not chunks or candidate != chunks[-1]:
            chunks.append(candidate)
    return chunks[:200]


def _token_count(text: str) -> int:
    return max(1, len(re.findall(r'\S+', text)))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _stable_chunk_id(resource_sha256: str, parser_version: str, index: int, normalized_text: str) -> str:
    return _sha256(f'{resource_sha256}:{parser_version}:{index}:{_sha256(normalized_text)}')


@transaction.atomic
def create_resource_with_chunks(*, type_: str, title: str, source_url: str, full_text: str, organization_id: str = '', proposal_id: int | None = None, evidence_purpose: str = 'fact', original_filename: str = '', mime_type: str = 'text/plain', parser_version: str = PARSER_VERSION, page_chunks: list[tuple[int, str, str]] | None = None, resource_sha256: str | None = None) -> AIResource:
    full_text = _normalize_text(full_text)
    if not full_text:
        raise IngestionError('empty_document')
    sha256 = resource_sha256 or AIResource.compute_sha256(full_text)
    existing = AIResource.objects.filter(organization_id=organization_id, sha256=sha256, parser_version=parser_version).first()
    if existing:
        return existing
    rows = page_chunks or [(1, chunk, '') for chunk in _chunk_text(full_text)]
    if not rows:
        raise IngestionError('empty_document')
    service = EmbeddingService.instance()
    resource = AIResource.objects.create(
        organization_id=organization_id, proposal_id=proposal_id, source_type=type_, evidence_purpose=evidence_purpose,
        title=title[:256], display_name=(title or original_filename)[:256], original_filename=original_filename[:512],
        mime_type=mime_type, source_url=source_url, sha256=sha256, parser_version=parser_version, metadata={'dedup': True},
    )
    for index, ((page, text, section_title), embedding) in enumerate(zip(rows, embed_texts([row[1] for row in rows]))):
        normalized = _normalize_text(text)
        AIChunk.objects.create(
            resource=resource, stable_chunk_id=_stable_chunk_id(sha256, parser_version, index, normalized), chunk_index=index,
            text=text, normalized_text=normalized, text_sha256=_sha256(normalized), page_start=page, page_end=page,
            section_title=section_title, token_count=_token_count(text), embedding_key=_sha256(normalized + str(len(embedding))),
            embedding=embedding, embedding_model=service.model_name, embedding_dimension=service.dim, metadata={},
        )
    AIResource.objects.filter(pk=resource.pk).update(
        embedding_model=service.model_name, embedding_revision=service.model_name, embedding_dimension=service.dim,
        page_count=max(row[0] for row in rows), metadata={'chunks': len(rows)},
    )
    return resource


def ingest_pdf(*, content: bytes, filename: str, organization_id: str, proposal_id: int | None = None, source_type: str = 'guideline', evidence_purpose: str = 'constraint', resource_sha256: str | None = None) -> AIResource:
    if not content.startswith(b'%PDF'):
        raise IngestionError('pdf_parse_failed')
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer
        pages = [ParsedPage(number, _normalize_text(''.join(item.get_text() for item in layout if isinstance(item, LTTextContainer)))) for number, layout in enumerate(extract_pages(BytesIO(content)), start=1)]
    except Exception as exc:
        raise IngestionError('pdf_parse_failed') from exc
    pages = [page for page in pages if page.text]
    if not pages:
        raise IngestionError('ocr_required')
    rows = [(page.page_number, chunk, '') for page in pages for chunk in _chunk_text(page.text)]
    if not rows:
        raise IngestionError('empty_document')
    return create_resource_with_chunks(
        type_=source_type, title=filename, source_url='', full_text='\n'.join(page.text for page in pages),
        organization_id=organization_id, proposal_id=proposal_id, evidence_purpose=evidence_purpose,
        original_filename=filename, mime_type='application/pdf', page_chunks=rows, resource_sha256=resource_sha256,
    )


def ingest_grant_call(url: str) -> AIResource:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return create_resource_with_chunks(type_='call_snapshot', title='Grant Call', source_url=url, full_text=_clean_html(response.text))


def ingest_manifest(yaml_text: str) -> list[AIResource]:
    items = (yaml.safe_load(yaml_text) or {}).get('items', [])
    resources: list[AIResource] = []
    for item in items:
        if not item.get('type') or not item.get('text'):
            continue
        resource = create_resource_with_chunks(type_=item['type'], title=item.get('title', item['type']), source_url=item.get('source_url', ''), full_text=item['text'])
        if resource not in resources:
            resources.append(resource)
    return resources
