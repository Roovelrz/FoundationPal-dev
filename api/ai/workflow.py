from __future__ import annotations

from uuid import UUID, uuid4

from .models import WorkflowRun


def resolve_run_id(value, *, proposal_id=None, org_id='', provider='', schema_version='v1') -> UUID:
    try:
        run_id = UUID(str(value)) if value else uuid4()
    except (TypeError, ValueError):
        run_id = uuid4()
    WorkflowRun.objects.get_or_create(
        run_id=run_id,
        defaults={
            'proposal_id': proposal_id,
            'org_id': org_id or '',
            'provider': provider or '',
            'schema_version': schema_version,
        },
    )
    return run_id
