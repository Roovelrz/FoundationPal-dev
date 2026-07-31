'''Thin Agent Harness for the existing proposal graph.'''

from typing import Any

from .proposal_graph import run_proposal_graph


def run_agent_task(
    task_type: str,
    organization_id: str,
    proposal_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not task_type:
        raise ValueError('task_type is required')
    if not organization_id:
        raise ValueError('organization_id is required')
    if not proposal_id:
        raise ValueError('proposal_id is required')
    if not isinstance(payload, dict):
        raise ValueError('payload must be a dictionary')
    if task_type != 'full_pipeline':
        raise ValueError('unsupported_task_type')

    result = run_proposal_graph({
        **payload,
        'organization_id': organization_id,
        'proposal_id': int(proposal_id),
    })
    status = result.get('status', 'failed')
    if status == 'awaiting_human_approval':
        status = 'needs_human_review'
    return {
        'task_type': task_type,
        'organization_id': organization_id,
        'proposal_id': proposal_id,
        'status': status,
        'output': result,
    }
