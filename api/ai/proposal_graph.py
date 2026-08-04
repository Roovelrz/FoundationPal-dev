'''LangGraph orchestration for the existing proposal services.'''

from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from langgraph.graph import END, START, StateGraph

from proposals.models import Proposal

from .section_pipeline import get_section
from .agent_boundaries import supervisor_next_agent, validate_agent_result
from .hitl import start_human_task
from .models import HumanApprovalTask, WorkflowRun
from .providers import get_provider
from .providers.base import normalize_application_system
from .services import ServiceError, finalize_service, plan_service, promote_service
from .tools import execute_tool
from .workflow import resolve_run_id


class ProposalWorkflowState(TypedDict, total=False):
    run_id: str
    thread_id: str
    organization_id: str
    application_system: str
    actor_id: int
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
    intake_profile: dict[str, Any]
    work_policy: dict[str, Any]
    grant_pack_version_id: int
    proposal_brief_version: int
    proposal_decision_ids: list[int]
    grill_session_id: int
    grill_mode: str
    requirement_ids: list[int]
    rule_evidence_ids: list[int]
    user_evidence_ids: list[int]
    claim_ids: list[int]
    requirement_gaps: list[int]
    evidence_gaps: list[int]
    validation_issues: list[dict[str, Any]]


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


def _create_section_approval_task(state: ProposalWorkflowState, section) -> None:
    try:
        run_id = UUID(str(state.get('run_id')))
    except (TypeError, ValueError):
        return
    workflow_run = WorkflowRun.objects.filter(run_id=run_id).first()
    if workflow_run is None:
        return
    review = state.get('review') or {}
    changes = review.get('required_changes') if isinstance(review.get('required_changes'), list) else []
    review_decision = review.get('decision') or 'human_review'
    review_summary = f'审查结论：{review_decision}'
    if changes:
        review_summary += '；修改要点：' + '；'.join(str(item)[:200] for item in changes[:3])
    task, created = HumanApprovalTask.objects.get_or_create(
        thread_id=f'{workflow_run.run_id}:section_approval',
        defaults={
            'workflow_run': workflow_run,
            'proposal_id': section.proposal_id,
            'node': 'section_approval',
            'input_json': {
                'section_key': section.key,
                'section_title': section.title,
                'draft_summary': (section.draft_content or section.approved_content or '').strip()[:500],
            },
            'model_output_json': {'review_summary': review_summary},
        },
    )
    if created:
        start_human_task({
            'thread_id': task.thread_id,
            'human_node': task.node,
            'human_input': task.input_json,
            'model_output': task.model_output_json,
        })


def _tool_caller(state: ProposalWorkflowState, proposal: Proposal):
    actor_id = state.get('actor_id')
    if actor_id:
        actor = get_user_model().objects.filter(id=actor_id).first()
        if actor is not None:
            return actor
    return proposal.author


def _execute_agent_tool(state: ProposalWorkflowState, *, caller_role: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    proposal = Proposal.objects.select_related('author').filter(id=state['proposal_id']).first()
    if proposal is None:
        raise ServiceError('proposal_not_found')
    result = execute_tool(
        schema_version='v1',
        tool_name=tool_name,
        arguments=arguments,
        caller_role=caller_role,
        caller=_tool_caller(state, proposal),
        organization_id=str(proposal.org_id),
        run_id=str(state.get('run_id') or ''),
    )
    if not result.success:
        raise ServiceError(result.error.error_code if result.error else 'tool_execution_failed')
    return result.data


def _ensure_run_context(state: ProposalWorkflowState) -> ProposalWorkflowState:
    proposal = Proposal.objects.filter(id=state.get('proposal_id')).only('id', 'org_id', 'author_id', 'content').first()
    if proposal is None:
        return state
    content = proposal.content or {}
    meta = content.get('meta') if isinstance(content, dict) else {}
    application_system = normalize_application_system(meta.get('application_system') if isinstance(meta, dict) else None)
    run_id = resolve_run_id(
        state.get('run_id'),
        proposal_id=proposal.id,
        org_id=str(proposal.org_id),
    )
    return {
        **state,
        'run_id': str(run_id),
        'organization_id': str(proposal.org_id),
        'actor_id': state.get('actor_id') or proposal.author_id,
        'application_system': application_system,
    }


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
        run_key = state.get('run_id') or ''
        _, handoff = validate_agent_result('writer', state)
        section = get_section(state['section_key'], proposal_id=state['proposal_id'])
        if section is None:
            raise ServiceError('section_not_found')
        draft = state.get('draft') or ''
        if attempt:
            review = state.get('review') or {}
            changes = review.get('required_changes') if isinstance(review.get('required_changes'), list) else []
            change_request = '\n'.join(str(change) for change in changes if str(change).strip())
            if not change_request:
                change_request = '根据评审意见修订本章草稿。'
            result = get_provider(getattr(settings, 'AI_PROVIDER', None)).revise(
                base_text=draft,
                change_request=change_request,
                deterministic=bool(getattr(settings, 'AI_DETERMINISTIC_SAMPLING', True)),
                application_system=normalize_application_system(state.get('application_system')),
            )
            draft = result.text.strip()
            if not draft:
                raise ServiceError('revision_empty')
        _execute_agent_tool(
            state,
            caller_role='writer',
            tool_name='save_section_draft',
            arguments={
                'proposal_id': state['proposal_id'],
                'section_id': section.key,
                'draft_markdown': draft,
                'answers': state.get('answers') or {},
                'idempotency_key': f'{run_key}:{node}:save_section_draft',
            },
        )
        return _success(state, node, draft=draft, handoffs=[*(state.get('handoffs') or []), handoff])
    except Exception as error:
        return _failure(state, 'writer', error)


def reviewer_node(state: ProposalWorkflowState) -> dict[str, Any]:
    attempt = int(state.get('revision_count', 0))
    node = f'reviewer:{attempt}'
    if _completed(state, node):
        return _append_trace(state, node, 'skipped')
    try:
        run_key = state.get('run_id') or ''
        queue = list(state.get('review_queue') or [])
        raw_review = queue.pop(0) if queue else state.get('review') or {}
        review_data = _execute_agent_tool(
            state,
            caller_role='reviewer',
            tool_name='submit_review',
            arguments={
                'proposal_id': state['proposal_id'],
                'section_id': state['section_key'],
                'review': raw_review,
                'idempotency_key': f'{run_key}:{node}:submit_review',
            },
        )
        review = review_data['review']
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
    try:
        section = get_section(state['section_key'], proposal_id=state['proposal_id'])
        if section is None:
            raise ServiceError('section_not_found')
        _create_section_approval_task(state, section)
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
    initial = _ensure_run_context({
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
    })
    return proposal_graph.invoke(initial, config={'recursion_limit': 30})
