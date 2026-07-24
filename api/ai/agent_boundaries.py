'''Fixed contracts and routing rules for the controlled three-agent workflow.'''

from __future__ import annotations

from typing import Any, TypedDict

from .validators import SchemaError, reviewer_or_human_review, section_draft, validate_planner_output


AGENT_NAMES = {'planner', 'writer', 'reviewer'}
AGENT_SCHEMAS = {'planner': 'ProposalPlan.v1', 'writer': 'SectionDraft.v1', 'reviewer': 'ReviewResult.v1'}
AGENT_TOOLS = {
    'planner': {'search_guideline', 'validate_constraints'},
    'writer': {'search_successful_cases', 'get_team_profile', 'save_section_draft'},
    'reviewer': {'validate_constraints', 'submit_review'},
}


class AgentHandoff(TypedDict):
    run_id: str
    node_name: str
    schema_version: str
    agent: str
    status: str


def supervisor_next_agent(*, phase: str) -> str:
    routes = {'plan': 'planner', 'write': 'writer', 'review': 'reviewer'}
    return routes.get(phase, 'human')


def validate_agent_result(agent: str, state: dict[str, Any]) -> tuple[dict[str, Any], AgentHandoff]:
    if agent not in AGENT_NAMES:
        raise SchemaError('unknown_agent')
    if agent == 'planner':
        plan = state.get('plan') or []
        if not plan:
            result = {'decision': 'human_review', 'reason': 'plan_missing'}
            status = 'human_review'
        else:
            result = validate_planner_output({'schema_version': 'v1', 'sections': plan})
            status = 'ok'
    elif agent == 'writer':
        result = section_draft(state.get('section_key') or '', state.get('draft') or '')
        result['evidence_ids'] = list(state.get('evidence_ids') or [])
        result['missing_evidence'] = [] if result['evidence_ids'] else ['evidence_not_supplied']
        status = 'ok'
    else:
        result = reviewer_or_human_review(state.get('review') or {})
        status = result['decision']
    handoff: AgentHandoff = {
        'run_id': str(state.get('run_id') or ''),
        'node_name': f'{agent}_agent',
        'schema_version': AGENT_SCHEMAS[agent],
        'agent': agent,
        'status': status,
    }
    return result, handoff
