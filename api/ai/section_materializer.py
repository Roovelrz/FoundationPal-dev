"""Section materialization service.

Consumes a planner blueprint (list of section descriptors) and ensures
`ProposalSection` rows exist and reflect planner-determined ordering and
titles. Idempotent and non-destructive: existing sections not present in
the new blueprint are left untouched (no deletion/archival yet).

Blueprint item schema:
  {"section_key": str, "title": str, "questions": list[str]}

Rules:
  - Keys normalized to lowercase slug-ish (keep alnum + dashes/underscores).
  - Order defaults to incremental index if not provided or invalid.
  - Planner inputs/questions are stored in metadata for UI restoration.
  - When creating, optional initial draft text seeds `draft_content`.
  - When updating existing section, we update title, order, and planner
    inputs only (never clobber draft/approved content here).
  - Returns list of (section, created_bool) in final applied order.

Future:
  - Handle planner-driven removal (archive or flag stale sections).
  - Enforce immutable key set post user edits (if needed).
"""

from __future__ import annotations
from typing import Iterable, Any
from django.db import transaction
from proposals.models import ProposalSection


def _normalize_key(raw: str) -> str:
    import re

    raw = (raw or '').strip().lower()
    # replace spaces with dashes, strip invalid chars
    raw = raw.replace(' ', '-')
    return re.sub(r'[^a-z0-9_-]', '', raw)[:128]


@transaction.atomic
def materialize_sections(*, proposal_id: int, blueprint: Iterable[dict[str, Any]]):
    out: list[tuple[ProposalSection, bool]] = []
    seen_keys: set[str] = set()
    fallback_ord = 0
    for idx, item in enumerate(blueprint or []):
        if not isinstance(item, dict):
            continue
        raw_key = item.get('section_key') or ''
        key = _normalize_key(str(raw_key))
        if not key or key in seen_keys:
            continue  # skip empties / duplicates
        seen_keys.add(key)
        order_val = item.get('order')
        try:
            order_int = int(order_val) if order_val is not None else idx
        except (TypeError, ValueError):  # pragma: no cover - defensive
            order_int = idx
        title_val = (item.get('title') or '').strip()[:256]
        raw_inputs = item.get('questions') or []
        inputs = [
            str(value).strip()[:500]
            for value in raw_inputs[:20]
            if str(value).strip()
        ] if isinstance(raw_inputs, list) else []
        created = False
        section = ProposalSection.objects.filter(proposal_id=proposal_id, key=key).first()
        if section is None:
            section = ProposalSection.objects.create(
                proposal_id=proposal_id,
                key=key,
                title=title_val,
                order=order_int,
                metadata={'questions': inputs},
            )
            created = True
        else:
            updates = {}
            if title_val and section.title != title_val:
                updates['title'] = title_val
            if section.order != order_int:
                updates['order'] = order_int
            if inputs:
                metadata = dict(section.metadata or {})
                if metadata.get('questions') != inputs:
                    metadata['questions'] = inputs
                    updates['metadata'] = metadata
            if updates:
                for k, v in updates.items():
                    setattr(section, k, v)
                section.save(update_fields=list(updates.keys()) + ['updated_at'])
        out.append((section, created))
        fallback_ord = max(fallback_ord, order_int + 1)
    return out


__all__ = ['materialize_sections']
