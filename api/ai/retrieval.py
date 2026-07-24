"""Dense retrieval used by RAG evaluation and Writer evidence injection."""

from __future__ import annotations

from typing import Sequence, Iterable
from math import sqrt
from .models import AIChunk
from .embedding_service import embed_texts


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = sqrt(sum(x * x for x in a)) or 1.0
    db = sqrt(sum(y * y for y in b)) or 1.0
    return num / (da * db)


def _trim_to_token_budget(chunks: Iterable[dict], *, max_tokens: int = 1200) -> list[dict]:
    out: list[dict] = []
    used = 0
    for ch in chunks:
        tlen = ch.get('token_count') or len(ch.get('text', '').split())
        if used + tlen > max_tokens:
            break
        used += tlen
        out.append(ch)
    return out


class RetrievalService:
    dense_top_k = 20
    final_top_k = 5

    def retrieve(
        self,
        query_text: str,
        *,
        organization_id: str | None = None,
        proposal_id: int | None = None,
        source_types: set[str] | None = None,
        dense_top_k: int | None = None,
        final_top_k: int | None = None,
        token_budget: int | None = None,
    ) -> list[dict]:
        if not query_text:
            return []
        q_vec = embed_texts([query_text])[0]
        chunks = AIChunk.objects.filter(resource__is_deleted=False, resource__status='ready').select_related('resource')
        if organization_id is not None:
            chunks = chunks.filter(resource__organization_id=organization_id)
        if proposal_id is not None:
            from django.db.models import Q

            chunks = chunks.filter(Q(resource__proposal_id__isnull=True) | Q(resource__proposal_id=proposal_id))
        if source_types:
            chunks = chunks.filter(resource__source_type__in=source_types)
        scored = []
        for ch in chunks[:500]:
            if ch.embedding:
                c_vec = ch.embedding
            else:
                c_vec = embed_texts([ch.text])[0]
                AIChunk.objects.filter(pk=ch.pk).update(embedding=c_vec)  # pragma: no cover
            scored.append((_cosine(q_vec, c_vec), ch))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        dense_limit = dense_top_k or self.dense_top_k
        final_limit = final_top_k or self.final_top_k
        out = []
        for dense_rank, (score, ch) in enumerate(scored[:dense_limit], start=1):
            if dense_rank > final_limit:
                break
            out.append({
                'chunk_id': ch.id,
                'resource_id': ch.resource_id,
                'score': round(score, 4),
                'dense_score': round(score, 4),
                'dense_rank': dense_rank,
                'final_rank': dense_rank,
                'text': ch.text,
                'type': ch.resource.source_type,
                'source_type': ch.resource.source_type,
                'token_count': ch.token_count,
                'document_name': ch.resource.display_name,
                'page_start': ch.page_start,
                'page_end': ch.page_end,
                'section_title': ch.section_title,
                'heading_path': ch.heading_path,
            })
        return _trim_to_token_budget(out, max_tokens=token_budget) if token_budget is not None else out


def retrieve_top_k(query_text: str, *, k: int = 6, token_budget: int | None = None, organization_id: str | None = None, proposal_id: int | None = None, source_types: set[str] | None = None) -> list[dict]:
    return RetrievalService().retrieve(
        query_text,
        organization_id=organization_id,
        proposal_id=proposal_id,
        source_types=source_types,
        dense_top_k=max(20, k),
        final_top_k=k,
        token_budget=token_budget,
    )


def retrieve_for_plan(grant_url: str | None, text_spec: str | None, *, token_budget: int | None = None) -> list[dict]:
    query = (text_spec or '') + ' ' + (grant_url or '')
    return retrieve_top_k(query.strip(), k=6, token_budget=token_budget)


def retrieve_for_section(section_id: str, answers: dict[str, str] | None, *, token_budget: int | None = None) -> list[dict]:
    base = section_id + ' ' + ' '.join((answers or {}).values())
    return retrieve_top_k(base.strip(), k=6, token_budget=token_budget)
