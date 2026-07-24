'''LangGraph orchestration for the existing proposal services.'''

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from proposals.models import Proposal

from .section_pipeline import get_section
from .agent_boundaries import supervisor_next_agent, validate_agent_result
from .services import ServiceError, finalize_service, plan_service, promote_service, review_service, write_service


class ProposalWorkflowState(TypedDict, total=False):
    run_id: str
    thread_id: str
    organization_id: str
    proposal_id: int
    section_key: str
    plan: list[dict[str, Any]]
    answers: dict[str, Any]
    evidence_ids: list[str]
    draft: str
    review: dict[str, Any]
    review_queue: list[dict[str, Any]]
    revision_count: int
    max_revisions: int
    status: str
    error: str
    max_node_retries: int
    node_retry_count: dict[str, int]
    idempotency_keys: dict[str, str]
    completed_nodes: list[str]
    trace: list[dict[str, str]]
    resume_after_approval: bool
    final_markdown: str
    handoffs: list[dict[str, str]]
    auto_approve: bool


def _append_trace(state: ProposalWorkflowState, node: str, status: str, error: str = '') -> dict[str, Any]:
    trace = list(state.get('trace') or [])
    trace.append({'node': node, 'status': status, 'error': error})
    return {'trace': trace, 'status': status, 'error': error}


def _completed(state: ProposalWorkflowState, node: str) -> bool:
    return node in (state.get('completed_nodes') or [])


def _success(state: ProposalWorkflowState, node: str, **updates: Any) -> dict[str, Any]:
    completed = list(state.get('completed_nodes') or [])
    if node not in completed:
        completed.append(node)
    result = _append_trace(state, node, 'completed')
    result['completed_nodes'] = completed
    result['idempotency_keys'] = {
        **(state.get('idempotency_keys') or {}),
        node: f"{state.get('run_id', '')}:{node}",
    }
    result.update(updates)
    return result


def _failure(state: ProposalWorkflowState, node: str, error: Exception) -> dict[str, Any]:
    retries = dict(state.get('node_retry_count') or {})
    retries[node] = retries.get(node, 0) + 1
    update = _append_trace(state, node, 'failed', str(error))
    update['node_retry_count'] = retries
    return update


def planner_node(state: ProposalWorkflowState) -> dict[str, Any]:
    if _completed(state, 'planner'):
        return _append_trace(state, 'planner', 'skipped')
    try:
        result, handoff = validate_agent_result('planner', state)
        if handoff['status'] == 'human_review':
            return _success(
                state,
                'planner',
                review={'decision': 'human_review'},
                handoffs=[*(state.get('handoffs') or []), handoff],
            )
        created = plan_service(proposal_id=state['proposal_id'], blueprint=state.get('plan') or [])
        return _success(state, 'planner', created_sections=created, handoffs=[*(state.get('handoffs') or []), handoff])
    except Exception as error:
        return _failure(state, 'planner', error)


def writer_node(state: ProposalWorkflowState) -> dict[str, Any]:
    attempt = int(state.get('revision_count', 0))
    node = f'writer:{attempt}'
    if _completed(state, node):
        return _append_trace(state, node, 'skipped')
    try:
        _, handoff = validate_agent_result('writer', state)
        section = get_section(state['section_key'], proposal_id=state['proposal_id'])
        if section is None:
            raise ServiceError('section_not_found')
        write_service(section=section, draft_markdown=state.get('draft') or '', answers=state.get('answers') or {})
        return _success(state, node, handoffs=[*(state.get('handoffs') or []), handoff])
    except Exception as error:
        return _failure(state, 'writer', error)


def reviewer_node(state: ProposalWorkflowState) -> dict[str, Any]:
    attempt = int(state.get('revision_count', 0))
    node = f'reviewer:{attempt}'
    if _completed(state, node):
        return _append_trace(state, node, 'skipped')
    try:
        queue = list(state.get('review_queue') or [])
        raw_review = queue.pop(0) if queue else state.get('review') or {}
        review = review_service(raw_review)
        _, handoff = validate_agent_result('reviewer', {**state, 'review': review})
        revision_count = attempt + 1 if review['decision'] == 'rewrite' else attempt
        return _success(
            state,
            node,
            review=review,
            review_queue=queue,
            revision_count=revision_count,
            handoffs=[*(state.get('handoffs') or []), handoff],
        )
    except Exception as error:
        return _failure(state, 'reviewer', error)


def human_node(state: ProposalWorkflowState) -> dict[str, Any]:
    if state.get('auto_approve') and (state.get('review') or {}).get('decision') == 'approve':
        try:
            section = get_section(state['section_key'], proposal_id=state['proposal_id'])
            if section is None:
                raise ServiceError('section_not_found')
            promote_service(section=section)
            proposal = Proposal.objects.get(id=state['proposal_id'])
            return _success(state, 'human', final_markdown=finalize_service(proposal=proposal), status='completed')
        except Exception as error:
            return _failure(state, 'human', error)
    return _success(state, 'human', status='awaiting_human_approval')


def finalize_node(state: ProposalWorkflowState) -> dict[str, Any]:
    if _completed(state, 'finalize'):
        return _append_trace(state, 'finalize', 'skipped')
    try:
        proposal = Proposal.objects.get(id=state['proposal_id'])
        final_markdown = finalize_service(proposal=proposal)
        return _success(state, 'finalize', final_markdown=final_markdown, status='completed')
    except Exception as error:
        return _failure(state, 'finalize', error)


def _entry_route(state: ProposalWorkflowState) -> str:
    return 'finalize' if state.get('resume_after_approval') else 'planner'


def _after_planner(state: ProposalWorkflowState) -> str:
    if state.get('error') or (state.get('review') or {}).get('decision') == 'human_review':
        return 'human'
    return supervisor_next_agent(phase='write')


def _after_writer(state: ProposalWorkflowState) -> str:
    if not state.get('error'):
        return supervisor_next_agent(phase='review')
    retries = (state.get('node_retry_count') or {}).get('writer', 0)
    return 'writer' if retries <= int(state.get('max_node_retries', 1)) else 'human'


def _after_reviewer(state: ProposalWorkflowState) -> str:
    if state.get('error'):
        return 'human'
    decision = (state.get('review') or {}).get('decision', 'human_review')
    if decision == 'rewrite' and int(state.get('revision_count', 0)) < int(state.get('max_revisions', 2)):
        return 'writer'
    return 'human'


def _after_finalize(state: ProposalWorkflowState) -> str:
    return 'human' if state.get('error') else END


def build_proposal_graph():
    graph = StateGraph(ProposalWorkflowState)
    graph.add_node('planner', planner_node)
    graph.add_node('writer', writer_node)
    graph.add_node('reviewer', reviewer_node)
    graph.add_node('human', human_node)
    graph.add_node('finalize', finalize_node)
    graph.add_conditional_edges(START, _entry_route, {'planner': 'planner', 'finalize': 'finalize'})
    graph.add_conditional_edges('planner', _after_planner, {'writer': 'writer', 'human': 'human'})
    graph.add_conditional_edges('writer', _after_writer, {'writer': 'writer', 'reviewer': 'reviewer', 'human': 'human'})
    graph.add_conditional_edges('reviewer', _after_reviewer, {'writer': 'writer', 'human': 'human'})
    graph.add_edge('human', END)
    graph.add_conditional_edges('finalize', _after_finalize, {'human': 'human', END: END})
    return graph.compile()


proposal_graph = build_proposal_graph()


def run_proposal_graph(state: ProposalWorkflowState) -> ProposalWorkflowState:
    initial: ProposalWorkflowState = {
        'revision_count': 0,
        'max_revisions': 2,
        'max_node_retries': 1,
        'status': 'running',
        'error': '',
        'trace': [],
        'completed_nodes': [],
        'idempotency_keys': {},
        'node_retry_count': {},
        'handoffs': [],
        **state,
    }
    return proposal_graph.invoke(initial, config={'recursion_limit': 30})
