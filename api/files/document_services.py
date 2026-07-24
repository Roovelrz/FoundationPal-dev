'''Shared PDF parsing services used by MCP tools and resources.'''

from __future__ import annotations

from io import BytesIO
from threading import BoundedSemaphore
from typing import Any

from django.conf import settings

from .services import read_controlled_upload


class DocumentServiceError(ValueError):
    def __init__(self, code: str, details: dict[str, Any] | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


_parse_slots = BoundedSemaphore(2)


def _limits() -> tuple[int, int]:
    return (
        int(getattr(settings, 'MCP_MAX_PDF_BYTES', 50 * 1024 * 1024)),
        int(getattr(settings, 'MCP_MAX_PDF_PAGES', 100)),
    )


def parse_pdf_bytes(content: bytes, *, filename: str = '') -> dict[str, Any]:
    '''Parse PDF text and page metadata with bounded size, page count, and concurrency.'''
    max_bytes, max_pages = _limits()
    if len(content) > max_bytes:
        raise DocumentServiceError('file_too_large', {'max_bytes': max_bytes})
    if not content.startswith(b'%PDF'):
        raise DocumentServiceError('pdf_parse_failed')
    if b'/Encrypt' in content:
        raise DocumentServiceError('pdf_encrypted')
    if not _parse_slots.acquire(blocking=False):
        raise DocumentServiceError('parse_concurrency_limited')
    try:
        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(content)) as pdf:
                if len(pdf.pages) > max_pages:
                    raise DocumentServiceError('page_limit_exceeded', {'max_pages': max_pages})
                pages = []
                for page_number, page in enumerate(pdf.pages, start=1):
                    text = (page.extract_text() or '').strip()
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    pages.append({
                        'page_number': page_number,
                        'text': text,
                        'text_chars': len(text),
                        'heading': lines[0][:200] if lines else '',
                    })
        except DocumentServiceError:
            raise
        except Exception as error:
            message = str(error).lower()
            if 'password' in message or 'encrypt' in message:
                raise DocumentServiceError('pdf_encrypted') from error
            raise DocumentServiceError('pdf_parse_failed') from error
    finally:
        _parse_slots.release()
    text_layer_pages = sum(1 for page in pages if page['text_chars'])
    if not text_layer_pages:
        raise DocumentServiceError('ocr_required', {'page_count': len(pages)})
    return {
        'schema_version': 'v1',
        'filename': filename,
        'page_count': len(pages),
        'text_layer_pages': text_layer_pages,
        'ocr_required': text_layer_pages != len(pages),
        'pages': pages,
    }


def parse_controlled_pdf(*, file_id: int, caller, organization_id: int, proposal_id: int | None = None) -> dict[str, Any]:
    '''Read an authorized file_id and parse it without accepting a file path.'''
    upload, content = read_controlled_upload(
        file_id=file_id,
        caller=caller,
        organization_id=organization_id,
        proposal_id=proposal_id,
    )
    if upload.content_type != 'application/pdf' and not upload.file.name.lower().endswith('.pdf'):
        raise DocumentServiceError('unsupported_document_type')
    result = parse_pdf_bytes(content, filename=upload.file.name.rsplit('/', 1)[-1])
    result['file_id'] = upload.id
    result['organization_id'] = upload.organization_id
    result['proposal_id'] = upload.proposal_id
    return result


def extract_document_structure(document: dict[str, Any]) -> dict[str, Any]:
    return {
        'schema_version': document['schema_version'],
        'file_id': document.get('file_id'),
        'page_count': document['page_count'],
        'sections': [
            {'index': index, 'page_number': page['page_number'], 'title': page['heading']}
            for index, page in enumerate(document['pages'], start=1)
        ],
    }


def extract_requirements(document: dict[str, Any]) -> dict[str, Any]:
    keywords = ('必须', '应当', '不得', '限制', '提交', '材料', 'require', 'must', 'shall')
    requirements = []
    for page in document['pages']:
        for line in page['text'].splitlines():
            normalized = line.strip()
            if normalized and any(keyword in normalized.lower() for keyword in keywords):
                requirements.append({'page_number': page['page_number'], 'text': normalized[:1000]})
    return {
        'schema_version': document['schema_version'],
        'file_id': document.get('file_id'),
        'requirements': requirements,
    }
