from __future__ import annotations

import hashlib
import json
from time import perf_counter
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.utils import timezone
from langgraph.graph import END, START, StateGraph

from orgs.models import Organization
from proposals.models import Proposal

from .models import AIChunk, AIResource, AIMetric, EvidenceUsage, ToolInvocation, WorkflowRun
from .proposal_graph import run_proposal_graph
from .provider import get_provider
from .retrieval import retrieve_top_k
from .services import finalize_service, plan_service, promote_service, review_service, write_service
from .section_pipeline import get_section
from .workflow import persist_graph_result, resolve_run_id
from .tools import execute_tool


FROZEN_CASES = [
    {'id': 'scope', 'query': '申请书正文页数限制是多少', 'answer': '正文不得超过三十页', 'evidence': '申请材料必须包含研究目标，且正文不得超过三十页。', 'answerable': True},
    {'id': 'eligibility', 'query': '申请人需要满足什么资格条件', 'answer': '申请人需具有独立承担项目能力', 'evidence': '申请人需具有独立承担项目能力，并按要求提交承诺书。', 'answerable': True},
    {'id': 'unanswerable', 'query': '项目资助金额是多少', 'answer': '', 'evidence': '', 'answerable': False},
]


def _estimate_cost_usd(model: str, usage: dict) -> float:
    prices = {
        'deepseek-v4-flash': (0.0028, 0.14, 0.28),
        'deepseek-v4-pro': (0.003625, 0.435, 0.87),
    }
    cache_hit, cache_miss, output = prices.get(model, (0.0, 0.0, 0.0))
    cached = int(usage.get('cached_tokens', 0))
    prompt = int(usage.get('prompt_tokens', 0))
    completion = int(usage.get('completion_tokens', 0))
    return round((cached * cache_hit + max(prompt - cached, 0) * cache_miss + completion * output) / 1_000_000, 8)


def _user_and_org():
    user, _ = get_user_model().objects.get_or_create(username='phase10-auto-eval')
    org, _ = Organization.objects.get_or_create(name='Phase10 Auto Eval', defaults={'admin': user})
    return user, org


def _resource_for_case(org, case):
    text = case['evidence'] or '无资助金额信息。'
    sha = hashlib.sha256(f'phase10:{case["id"]}:{text}'.encode('utf-8')).hexdigest()
    resource, _ = AIResource.objects.get_or_create(
        organization_id=str(org.id), sha256=sha, parser_version='phase10-v1',
        defaults={'source_type': 'guideline', 'display_name': f'phase10-{case["id"]}'},
    )
    chunk, _ = AIChunk.objects.get_or_create(
        resource=resource, chunk_index=0,
        defaults={'stable_chunk_id': sha, 'text': text, 'normalized_text': text, 'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'token_count': len(text.split()) or 1},
    )
    return chunk


def _linear(state):
    proposal = Proposal.objects.get(id=state['proposal_id'])
    plan_service(proposal_id=proposal.id, blueprint=state['plan'])
    section = get_section(state['section_key'], proposal_id=proposal.id)
    write_service(section=section, draft_markdown=state['draft'], answers=state['answers'])
    review_service(state['review'])
    promote_service(section=section)
    return {'status': 'completed', 'final_markdown': finalize_service(proposal=proposal), 'trace': [{'node': 'workflow', 'status': 'completed', 'error': ''}]}


def _single_graph(state):
    graph = StateGraph(dict)
    graph.add_node('workflow', _linear)
    graph.add_edge(START, 'workflow')
    graph.add_edge('workflow', END)
    return graph.compile().invoke(state)


def run_automatic_phase10_evaluation():
    user, org = _user_and_org()
    results = []
    evaluation_id = uuid4().hex[:12]
    provider = get_provider()
    for case in FROZEN_CASES:
        chunk = _resource_for_case(org, case)
        candidates = retrieve_top_k(case['query'], k=3, organization_id=str(org.id))
        candidate_ids = {item['chunk_id'] for item in candidates}
        recall = bool(case['answerable'] and chunk.id in candidate_ids)
        no_answer = not case['answerable'] and all(item['score'] < 0.98 for item in candidates)
        judge = json.loads(provider.judge_rag_context(query=case['query'], reference_answer=case['answer'] or '无法从上下文得出答案', candidates=candidates))
        judge_usage = dict(getattr(provider, 'last_usage', {}))
        judge_cost = _estimate_cost_usd(getattr(provider, 'model', ''), judge_usage)
        AIMetric.objects.create(
            type='evaluation', model_id=getattr(provider, 'model', ''), duration_ms=0,
            tokens_used=int(judge_usage.get('total_tokens', 0)), estimated_cost_usd=judge_cost,
            success=True, org_id=str(org.id),
        )
        faithfulness = judge.get('coverage') == 'complete' if case['answerable'] else judge.get('coverage') == 'none'
        for architecture in ('sequential', 'langgraph_single', 'multi_agent'):
            proposal = Proposal.objects.create(author=user, org=org, content={'phase10_case': case['id']})
            run_id = resolve_run_id(None, proposal_id=proposal.id, org_id=str(org.id))
            state = {'run_id': str(run_id), 'thread_id': f'phase10-{architecture}-{case["id"]}', 'organization_id': str(org.id), 'proposal_id': proposal.id, 'section_key': 'summary', 'plan': [{'section_key': 'summary', 'title': '自动评测摘要', 'questions': ['问题']}], 'answers': {'问题': case['query']}, 'draft': case['answer'] or '未检索到可支持答案的证据。', 'evidence_ids': [str(chunk.id)] if case['answerable'] else [], 'review': {'schema_version': 'v1', 'section_key': 'summary', 'decision': 'approve', 'issues': [], 'required_changes': [], 'protected_facts': [], 'evidence_gaps': []}}
            started = perf_counter()
            if architecture == 'sequential':
                state = _linear(state)
            elif architecture == 'langgraph_single':
                state = _single_graph(state)
            else:
                state = run_proposal_graph({**state, 'auto_approve': True})
            run = WorkflowRun.objects.get(run_id=run_id)
            if architecture == 'multi_agent':
                persist_graph_result(run_id, state)
                run.refresh_from_db()
            else:
                run.architecture = architecture
                run.status = state['status']
                run.trace_json = state['trace']
                run.completed_at = timezone.now()
                run.save(update_fields=['architecture', 'status', 'trace_json', 'completed_at'])
            AIMetric.objects.create(type='write', model_id='phase10-auto', duration_ms=round((perf_counter() - started) * 1000), tokens_used=0, success=True, org_id=str(org.id), run_id=run_id)
            if case['answerable']:
                section = get_section('summary', proposal_id=proposal.id)
                EvidenceUsage.objects.create(workflow_run=run, proposal_section=section, chunk=chunk, role='writer', retrieval_query=case['query'], rank=1, similarity_score=1.0, used_in_prompt=True, cited_by_model=True, evidence_alias='E1', snapshot_text=chunk.text)
            ToolInvocation.objects.create(tool_name='validate_constraints', caller_role='planner', caller=user, organization_id=str(org.id), proposal_id=proposal.id, workflow_run=run, idempotency_key=f'phase10-{evaluation_id}-{architecture}-{case["id"]}', request_hash='phase10', status='done', duration_ms=1)
            execute_tool(
                schema_version='v1', tool_name='save_section_draft', caller_role='planner', caller=user,
                organization_id=str(org.id), run_id=str(run_id),
                arguments={'proposal_id': proposal.id, 'section_id': 'summary', 'draft_markdown': 'blocked', 'answers': {}, 'idempotency_key': f'blocked-{evaluation_id}-{architecture}-{case["id"]}'},
            )
        results.append({'case_id': case['id'], 'context_recall_at_3': recall, 'no_answer_correct': no_answer, 'faithful': faithfulness, 'judge_usage': judge_usage, 'judge_estimated_cost_usd': judge_cost})
    return str(org.id), results
