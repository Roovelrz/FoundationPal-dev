from __future__ import annotations

from uuid import UUID, uuid4

from django.utils import timezone

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


def persist_graph_result(run_id, state) -> None:
    run = WorkflowRun.objects.filter(run_id=run_id).first()
    if run is None:
        return
    status = state.get('status') or 'error'
    run.architecture = 'multi_agent'
    run.status = status
    run.trace_json = list(state.get('trace') or [])
    run.handoffs_json = list(state.get('handoffs') or [])
    run.revision_count = int(state.get('revision_count') or 0)
    run.fallback_mode = 'human' if status == 'awaiting_human_approval' else ''
    run.resumed_from_checkpoint = bool(state.get('resume_after_approval'))
    run.completed_at = timezone.now()
    run.save(update_fields=[
        'architecture', 'status', 'trace_json', 'handoffs_json', 'revision_count',
        'fallback_mode', 'resumed_from_checkpoint', 'completed_at',
    ])
