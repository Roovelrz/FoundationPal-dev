'''Fixed-schema tool registry for controlled proposal workflow calls.'''

from __future__ import annotations

import hashlib
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

from django.db import transaction

from proposals.models import Proposal

from .models import AIResource, Claim, ClaimEvidenceBinding, GrantPackVersion, GrantRequirement, ProposalBrief, ToolInvocation, UserEvidence, WorkflowRun
from .section_pipeline import get_section
from .services import (
    ServiceError,
    export_service,
    promote_service,
    review_service,
    write_service,
)
from .validators import SCHEMA_VERSION, ToolResult, WorkflowError
from .claim_planning import coverage
from .domain_retrieval import EvidenceQuery, RuleQuery
from .query_router import search_grant_rules, search_user_evidence


TOOL_ACCESS = {
    'search_guideline': {'planner'},
    'search_successful_cases': {'writer'},
    'get_team_profile': {'writer'},
    'save_section_draft': {'writer'},
    'validate_constraints': {'planner', 'reviewer'},
    'submit_review': {'reviewer'},
    'promote_section': {'user'},
    'export_proposal': {'user'},
    'search_grant_rules': {'planner', 'writer', 'reviewer'},
    'search_user_evidence': {'writer', 'reviewer'},
    'get_grant_pack_schema': {'planner', 'writer', 'reviewer'},
    'get_requirement_source': {'planner', 'writer', 'reviewer'},
    'get_user_evidence_source': {'writer', 'reviewer'},
    'get_proposal_brief': {'planner', 'writer', 'reviewer'},
    'get_work_policy': {'planner', 'writer', 'reviewer'},
    'validate_rule_coverage': {'reviewer'},
    'validate_claim_support': {'reviewer'},
    'save_claim_binding': {'reviewer'},
}

SIDE_EFFECT_TOOLS = {'save_section_draft', 'submit_review', 'promote_section', 'export_proposal', 'save_claim_binding'}

TOOL_ARGUMENTS = {
    'search_guideline': {'proposal_id', 'query'},
    'search_successful_cases': {'proposal_id', 'query'},
    'get_team_profile': {'proposal_id'},
    'save_section_draft': {'proposal_id', 'section_id', 'draft_markdown', 'answers', 'idempotency_key'},
    'validate_constraints': {'proposal_id'},
    'submit_review': {'proposal_id', 'section_id', 'review', 'idempotency_key'},
    'promote_section': {'proposal_id', 'section_id', 'idempotency_key'},
    'export_proposal': {'proposal_id', 'format', 'idempotency_key'},
    'search_grant_rules': {'proposal_id', 'pack_version_id', 'query'},
    'search_user_evidence': {'proposal_id', 'query'},
    'get_grant_pack_schema': {'proposal_id', 'pack_version_id'},
    'get_requirement_source': {'proposal_id', 'requirement_id'},
    'get_user_evidence_source': {'proposal_id', 'user_evidence_id'},
    'get_proposal_brief': {'proposal_id'},
    'get_work_policy': {'proposal_id'},
    'validate_rule_coverage': {'proposal_id', 'claim_plan_id'},
    'validate_claim_support': {'proposal_id', 'claim_id'},
    'save_claim_binding': {'proposal_id', 'claim_id', 'user_evidence_id', 'idempotency_key'},
}


def _error(tool_name: str, code: str, message: str) -> ToolResult:
    return ToolResult(
        schema_version=SCHEMA_VERSION,
        tool_name=tool_name,
        success=False,
        data={},
        error=WorkflowError(error_code=code, message=message),
    )


def _audit_rejection(*, tool_name: str, caller_role: str, caller, organization_id: str, proposal, run_id, error_code: str) -> None:
    workflow_run = WorkflowRun.objects.filter(run_id=run_id).first() if run_id else None
    if caller is None or proposal is None or workflow_run is None:
        return
    ToolInvocation.objects.create(
        tool_name=tool_name,
        caller_role=caller_role,
        caller=caller,
        organization_id=str(organization_id),
        proposal_id=proposal.id,
        workflow_run=workflow_run,
        idempotency_key=f'rejected:{uuid4()}',
        status='rejected',
        error_code=error_code,
    )


def _validate_input(tool_name: str, arguments: Any) -> str | None:
    if tool_name not in TOOL_ACCESS:
        return 'unknown_tool'
    if not isinstance(arguments, dict):
        return 'arguments_wrong_type'
    if set(arguments) != TOOL_ARGUMENTS[tool_name]:
        return 'arguments_schema_mismatch'
    if not isinstance(arguments['proposal_id'], int):
        return 'proposal_id_wrong_type'
    if tool_name in {'search_guideline', 'search_successful_cases'} and not isinstance(arguments['query'], str):
        return 'query_wrong_type'
    if tool_name in {'search_grant_rules', 'search_user_evidence'} and not isinstance(arguments['query'], str):
        return 'query_wrong_type'
    for name in ('search_grant_rules', 'get_grant_pack_schema'):
        if tool_name == name and not isinstance(arguments['pack_version_id'], int):
            return 'pack_version_id_wrong_type'
    if tool_name == 'save_section_draft':
        if not isinstance(arguments['section_id'], str) or not isinstance(arguments['draft_markdown'], str) or not isinstance(arguments['answers'], dict):
            return 'draft_arguments_wrong_type'
    if tool_name == 'submit_review':
        if not isinstance(arguments['section_id'], str) or not isinstance(arguments['review'], dict):
            return 'review_arguments_wrong_type'
    if tool_name in {'promote_section'} and not isinstance(arguments['section_id'], str):
        return 'section_id_wrong_type'
    if tool_name == 'export_proposal' and arguments['format'] not in {'md', 'pdf', 'docx'}:
        return 'format_invalid'
    if tool_name in SIDE_EFFECT_TOOLS or tool_name == 'save_claim_binding':
        key = arguments.get('idempotency_key')
        if not isinstance(key, str) or not key.strip() or len(key) > 128:
            return 'idempotency_key_invalid'
    return None


def _resource_data(*, proposal_id: int, organization_id: str, source_type: str) -> list[dict[str, Any]]:
    resources = AIResource.objects.filter(
        organization_id=organization_id,
        source_type=source_type,
        is_deleted=False,
        status='ready',
    ).filter(proposal_id__in=[None, proposal_id]).order_by('-created_at')[:10]
    return [{'id': resource.id, 'name': resource.display_name or resource.title, 'source_type': resource.source_type} for resource in resources]


def _execute(tool_name: str, arguments: dict[str, Any], proposal: Proposal) -> dict[str, Any]:
    if tool_name == 'search_guideline':
        return {'resources': _resource_data(proposal_id=proposal.id, organization_id=str(proposal.org_id), source_type='guideline')}
    if tool_name == 'search_successful_cases':
        return {'resources': _resource_data(proposal_id=proposal.id, organization_id=str(proposal.org_id), source_type='successful_case')}
    if tool_name == 'get_team_profile':
        return {'resources': _resource_data(proposal_id=proposal.id, organization_id=str(proposal.org_id), source_type='team_profile')}
    if tool_name == 'save_section_draft':
        section = get_section(arguments['section_id'], proposal_id=proposal.id)
        if section is None:
            raise ServiceError('section_not_found')
        write_service(section=section, draft_markdown=arguments['draft_markdown'], answers=arguments['answers'])
        return {'section_id': section.id, 'status': 'saved'}
    if tool_name == 'validate_constraints':
        approved = proposal.sections.filter(state='approved').count()
        total = proposal.sections.count()
        return {'valid': total > 0, 'section_count': total, 'approved_section_count': approved}
    if tool_name == 'submit_review':
        review = review_service(arguments['review'])
        return {'section_id': arguments['section_id'], 'review': review}
    if tool_name == 'promote_section':
        section = get_section(arguments['section_id'], proposal_id=proposal.id)
        if section is None:
            raise ServiceError('section_not_found')
        promote_service(section=section)
        return {'section_id': section.id, 'status': 'promoted'}
    if tool_name == 'export_proposal':
        return {'format': arguments['format'], 'markdown': export_service(proposal=proposal)}
    if tool_name == 'search_grant_rules':
        return {'knowledge_domain': 'grant_rule', **search_grant_rules(RuleQuery(pack_version_id=arguments['pack_version_id'], user_question=arguments['query']))}
    if tool_name == 'search_user_evidence':
        return {'knowledge_domain': 'user_evidence', **search_user_evidence(EvidenceQuery(organization_id=str(proposal.org_id), proposal_id=proposal.id, user_question=arguments['query']))}
    if tool_name == 'get_grant_pack_schema':
        version = GrantPackVersion.objects.filter(pk=arguments['pack_version_id'], status='published').first()
        if version is None:
            raise ServiceError('published_grant_pack_required')
        return {'knowledge_domain': 'grant_rule', 'pack_version_id': version.id, 'sections': list(version.section_schemas.values('section_key', 'title', 'order', 'word_limit'))}
    if tool_name == 'get_requirement_source':
        requirement = GrantRequirement.objects.filter(pk=arguments['requirement_id'], pack_version__status='published').select_related('source_chunk__resource').first()
        if requirement is None:
            raise ServiceError('requirement_not_found')
        return {'knowledge_domain': 'grant_rule', 'requirement_id': requirement.id, 'source': requirement.source_chunk.resource.display_name, 'excerpt': requirement.source_excerpt or requirement.text}
    if tool_name == 'get_user_evidence_source':
        evidence = UserEvidence.objects.filter(pk=arguments['user_evidence_id'], organization_id=str(proposal.org_id)).select_related('chunk__resource').first()
        if evidence is None or (evidence.proposal_id and evidence.proposal_id != proposal.id):
            raise ServiceError('user_evidence_not_found')
        return {'knowledge_domain': 'user_evidence', 'user_evidence_id': evidence.id, 'source': evidence.chunk.resource.display_name, 'excerpt': evidence.controlled_summary or evidence.chunk.text[:1000]}
    if tool_name == 'get_proposal_brief':
        brief = ProposalBrief.objects.filter(proposal=proposal, confirmed=True).order_by('-id').first()
        if brief is None:
            raise ServiceError('confirmed_proposal_brief_required')
        return {'proposal_brief_version': brief.version, 'content': brief.content}
    if tool_name == 'get_work_policy':
        brief = ProposalBrief.objects.filter(proposal=proposal, confirmed=True).select_related('session__policy').order_by('-id').first()
        if brief is None:
            raise ServiceError('confirmed_proposal_brief_required')
        policy = brief.session.policy
        return {'policy_version': policy.version, 'grill_mode': policy.grill_mode, 'question_budget': policy.question_budget, 'preserve_user_structure': policy.preserve_user_structure}
    if tool_name == 'validate_rule_coverage':
        from .models import ClaimPlan
        plan = ClaimPlan.objects.filter(pk=arguments['claim_plan_id'], proposal=proposal).first()
        if plan is None:
            raise ServiceError('claim_plan_not_found')
        return {'knowledge_domain': 'grant_rule', **coverage(plan)}
    if tool_name == 'validate_claim_support':
        claim = Claim.objects.filter(pk=arguments['claim_id'], proposal=proposal).first()
        if claim is None:
            raise ServiceError('claim_not_found')
        return {'knowledge_domain': 'user_evidence', 'claim_id': claim.id, 'support_count': claim.evidence_bindings.filter(user_evidence__isnull=False).count(), 'status': claim.status}
    if tool_name == 'save_claim_binding':
        claim = Claim.objects.filter(pk=arguments['claim_id'], proposal=proposal).first()
        evidence = UserEvidence.objects.filter(pk=arguments['user_evidence_id'], organization_id=str(proposal.org_id)).first()
        if claim is None or evidence is None:
            raise ServiceError('claim_or_evidence_not_found')
        binding, _ = ClaimEvidenceBinding.objects.get_or_create(claim=claim, user_evidence=evidence, defaults={'support_type': 'reviewer_confirmed', 'support_strength': 'partial', 'reviewer_status': 'pending'})
        return {'claim_id': claim.id, 'user_evidence_id': evidence.id, 'binding_id': binding.id}
    raise ServiceError('unknown_tool')


def execute_tool(*, schema_version: str, tool_name: str, arguments: dict[str, Any], caller_role: str,
                 caller, organization_id: str, run_id: str | None = None) -> ToolResult:
    '''Validate, authorize, audit, and execute one controlled tool call.'''
    if schema_version != SCHEMA_VERSION:
        return _error(tool_name, 'unsupported_schema_version', 'unsupported schema_version')
    invalid = _validate_input(tool_name, arguments)
    if invalid:
        return _error(tool_name, 'invalid_tool_input', invalid)
    if caller_role not in TOOL_ACCESS[tool_name]:
        proposal = Proposal.objects.filter(id=arguments['proposal_id']).first()
        _audit_rejection(
            tool_name=tool_name, caller_role=caller_role, caller=caller,
            organization_id=organization_id, proposal=proposal, run_id=run_id,
            error_code='tool_not_authorized',
        )
        return _error(tool_name, 'tool_not_authorized', 'caller role is not allowed to use this tool')
    if caller is None:
        return _error(tool_name, 'caller_required', 'authenticated caller is required')
    proposal = Proposal.objects.filter(id=arguments['proposal_id']).first()
    if proposal is None:
        return _error(tool_name, 'proposal_not_found', 'proposal does not exist')
    if str(proposal.org_id) != str(organization_id):
        return _error(tool_name, 'workspace_forbidden', 'proposal is outside the caller workspace')
    workflow_run = WorkflowRun.objects.filter(run_id=run_id).first() if run_id else None
    if tool_name in SIDE_EFFECT_TOOLS and workflow_run is None:
        return _error(tool_name, 'run_id_required', 'side-effect tools require an existing run_id')
    request_hash = hashlib.sha256(json.dumps(arguments, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    key = arguments.get('idempotency_key', '')
    with transaction.atomic():
        if tool_name in SIDE_EFFECT_TOOLS:
            previous = ToolInvocation.objects.select_for_update().filter(
                tool_name=tool_name,
                caller_role=caller_role,
                caller=caller,
                organization_id=str(organization_id),
                idempotency_key=key,
            ).first()
            if previous is not None:
                if previous.request_hash != request_hash:
                    return _error(tool_name, 'idempotency_key_conflict', 'idempotency key was already used with different arguments')
                previous.replay_count += 1
                previous.save(update_fields=['replay_count', 'updated_at'])
                return ToolResult(schema_version=SCHEMA_VERSION, tool_name=tool_name, success=previous.status == 'done', data=previous.result_json,
                                  error=WorkflowError(previous.error_code, previous.error_code) if previous.error_code else None)
        invocation = ToolInvocation.objects.create(
            tool_name=tool_name,
            caller_role=caller_role,
            caller=caller,
            organization_id=str(organization_id),
            proposal_id=proposal.id,
            workflow_run=workflow_run,
            idempotency_key=key,
            request_hash=request_hash,
        )
        started = perf_counter()
        try:
            data = _execute(tool_name, arguments, proposal)
        except ServiceError as error:
            invocation.status = 'error'
            invocation.error_code = error.code
            invocation.duration_ms = round((perf_counter() - started) * 1000)
            invocation.save(update_fields=['status', 'error_code', 'duration_ms', 'updated_at'])
            return _error(tool_name, error.code, error.code)
        invocation.result_json = data
        invocation.duration_ms = round((perf_counter() - started) * 1000)
        invocation.save(update_fields=['result_json', 'duration_ms', 'updated_at'])
    return ToolResult(schema_version=SCHEMA_VERSION, tool_name=tool_name, success=True, data=data)
