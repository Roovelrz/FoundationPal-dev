import uuid
from dataclasses import dataclass

from django.db import transaction

from .domain_retrieval import EvidenceQuery, RuleQuery
from .models import (
    AssumptionRegister, EvidenceFact, GrantPackVersion, GrillAnswer, GrillDecisionNode,
    GrillSession, ProposalBrief, ProposalDecision, ProposalDecisionLedger,
    ProposalIntakeProfile, ProposalWorkPolicy, UserEvidence,
)
from .query_router import intake_knowledge_snapshot, retrieve_dual


DISCOVERY_TOPICS = (
    ('research_object', '请确认本项目聚焦的研究对象。', True, 10),
    ('core_problem', '请确认项目要解决的核心科学问题。', True, 20),
    ('research_goal', '请确认项目的研究目标。', True, 30),
    ('research_contents', '请确认拟开展的主要研究内容。', True, 40),
    ('methodology', '请确认支撑研究目标的技术路线。', True, 50),
    ('innovation_focus', '请确认最需要突出的一项创新方向。', True, 60),
    ('expected_outputs', '请确认预期成果。', False, 70),
)
REFINEMENT_TOPICS = (
    ('preserve_structure', '请确认必须保留的现有结构或表述。', True, 10),
    ('research_goal', '请确认现有目标需要保留或调整的部分。', True, 20),
    ('research_contents', '请确认研究内容之间需要消除的重复或缺口。', True, 30),
    ('methodology', '请确认技术路线需要补强的环节。', True, 40),
    ('innovation_focus', '请确认需要保留的实质创新点。', True, 50),
)

REVIEW_PROFILE = {
    'mode': 'review',
    'input_types': ['ReviewIssue', 'EvidenceGap', 'RuleGap', 'Conflict'],
    'question_types': ['review_decision', 'conflict_confirmation'],
    'enabled': False,
}


def _latest_draft(proposal):
    sections = list(proposal.sections.all())
    texts = [item.draft_content or item.approved_content or item.content for item in sections]
    return '\n'.join(item for item in texts if item).strip()


def detect_profile(proposal, *, task_mode, quality_level, inputs):
    raw_version = (inputs or {}).get('pack_version_id')
    raw_generic_version = (inputs or {}).get('generic_pack_version_id')
    try:
        version = GrantPackVersion.objects.filter(pk=int(raw_version), status='published').first() if raw_version else None
    except (TypeError, ValueError):
        version = None
    try:
        generic_version = GrantPackVersion.objects.select_related('pack__program').filter(
            pk=int(raw_generic_version), status='published', pack__program__program_type='generic',
        ).first() if raw_generic_version and not raw_version else None
    except (TypeError, ValueError):
        generic_version = None
    rule_readiness = 'verified_pack' if version else ('uploaded_pending' if raw_version else ('generic_fallback' if generic_version else 'missing_blocking'))
    text = _latest_draft(proposal)
    if not text:
        content_maturity = 'none'
    elif len(text) < 800:
        content_maturity = 'rough_notes'
    elif len(text) < 3000:
        content_maturity = 'outline'
    elif len(text) < 8000:
        content_maturity = 'partial_draft'
    else:
        content_maturity = 'full_draft'
    evidence = UserEvidence.objects.filter(organization_id=str(proposal.org_id))
    confirmed_facts = EvidenceFact.objects.filter(user_evidence__in=evidence, verification_status='user_confirmed').exists()
    extracted_facts = EvidenceFact.objects.filter(user_evidence__in=evidence, verification_status='extracted').exists()
    evidence_readiness = 'verified' if confirmed_facts else ('sufficient' if extracted_facts else ('partial' if evidence.exists() else 'none'))
    return {
        'rule_readiness': rule_readiness,
        'content_maturity': content_maturity,
        'evidence_readiness': evidence_readiness,
        'detected_inputs': {
            'pack_version_id': version.id if version else None,
            'generic_pack_version_id': generic_version.id if generic_version else None,
            'has_draft': bool(text), 'user_evidence_count': evidence.count(),
        },
    }


def intake_route(*, task_mode, quality_level, rule_readiness, content_maturity, evidence_readiness):
    if task_mode == 'polish_existing' and quality_level == 'quick' and content_maturity == 'full_draft':
        return 'review' if rule_readiness == 'uploaded_pending' else 'skip'
    if rule_readiness == 'missing_blocking':
        return 'evidence_confirmation'
    if task_mode == 'polish_existing' and quality_level != 'quick' and (
        (rule_readiness == 'verified_pack' and evidence_readiness in ('none', 'partial'))
        or (rule_readiness == 'generic_fallback' and evidence_readiness == 'none')
    ):
        return 'evidence_confirmation'
    if task_mode == 'polish_existing':
        return 'review'
    if task_mode == 'refine_outline':
        return 'refinement'
    return 'discovery'


def build_policy(profile):
    grill_mode = intake_route(
        task_mode=profile.task_mode,
        quality_level=profile.quality_level,
        rule_readiness=profile.rule_readiness,
        content_maturity=profile.content_maturity,
        evidence_readiness=profile.evidence_readiness,
    )
    if grill_mode == 'skip':
        budget = 0
    elif profile.task_mode == 'plan_from_scratch' and profile.rule_readiness == 'missing_blocking':
        budget = {'quick': 2, 'standard': 3, 'deep': 3}[profile.quality_level]
    elif profile.task_mode == 'polish_existing' and profile.rule_readiness == 'missing_blocking':
        budget = 4
    else:
        budget = {'quick': 3, 'standard': 6, 'deep': 8}[profile.quality_level]
        if profile.task_mode == 'plan_from_scratch' and profile.rule_readiness in ('verified_pack', 'uploaded_pending'):
            budget += 1 if profile.quality_level != 'deep' else 2
        elif profile.task_mode == 'plan_from_scratch' and profile.rule_readiness == 'generic_fallback' and profile.quality_level == 'deep':
            budget += 1
        elif profile.task_mode == 'refine_outline' and profile.rule_readiness == 'generic_fallback' and profile.quality_level in ('quick', 'standard'):
            budget -= 1
        elif profile.task_mode == 'refine_outline' and profile.quality_level == 'quick' and profile.content_maturity == 'partial_draft':
            budget = 2
        elif profile.task_mode == 'polish_existing' and profile.quality_level == 'quick' and profile.content_maturity != 'full_draft':
            budget = 2
        elif profile.task_mode == 'polish_existing' and profile.quality_level == 'quick' and profile.rule_readiness == 'uploaded_pending':
            budget = 1
        elif profile.task_mode == 'polish_existing' and profile.quality_level == 'standard':
            budget = 4 if profile.rule_readiness == 'uploaded_pending' or profile.evidence_readiness == 'partial' else 3
        elif profile.task_mode == 'polish_existing' and profile.quality_level == 'deep':
            budget = 6
    return {
        'grill_mode': grill_mode,
        'question_budget': budget,
        'preserve_user_structure': grill_mode == 'refinement',
        'planning_mode': 'preserve' if grill_mode == 'refinement' else 'rebuild',
        'writing_mode': profile.quality_level,
        'allowed_assumptions': ['low_risk'] if profile.quality_level == 'quick' else [],
        'enabled_reviewers': ['rule', 'fact'] if profile.quality_level != 'quick' else [],
        'max_auto_revisions': 0,
        'blocking_policy': {'require_rule_pack': profile.quality_level == 'deep', 'allow_low_risk_assumptions': profile.quality_level == 'quick'},
    }


def _knowledge_snapshot(proposal, profile):
    pack_version_id = profile.detected_inputs.get('pack_version_id')
    result = retrieve_dual(
        question='基金规则要求与团队已有基础',
        rule_query=RuleQuery(pack_version_id=pack_version_id, user_question='基金规则要求') if pack_version_id else None,
        evidence_query=EvidenceQuery(organization_id=str(proposal.org_id), proposal_id=proposal.id, user_question='团队已有基础'),
    )
    return intake_knowledge_snapshot(result)


def _topics(mode):
    return REFINEMENT_TOPICS if mode == 'refinement' else DISCOVERY_TOPICS


@transaction.atomic
def start_intake(proposal, *, task_mode, quality_level, inputs=None, user_overrides=None):
    detected = detect_profile(proposal, task_mode=task_mode, quality_level=quality_level, inputs=inputs or {})
    version = (ProposalIntakeProfile.objects.filter(proposal=proposal).order_by('-version').values_list('version', flat=True).first() or 0) + 1
    profile = ProposalIntakeProfile.objects.create(
        proposal=proposal, organization_id=str(proposal.org_id), version=version,
        task_mode=task_mode, quality_level=quality_level, user_overrides=user_overrides or {}, **detected,
    )
    content = dict(proposal.content or {})
    meta = dict(content.get('meta') or {})
    meta['intake_snapshot'] = {
        'task_mode': task_mode,
        'quality_level': quality_level,
        'material_references': dict(inputs or {}),
        'rule_pack_version_id': detected['detected_inputs']['pack_version_id'],
        'profile_version': version,
    }
    content['meta'] = meta
    proposal.content = content
    proposal.save(update_fields=['content', 'last_edited'])
    policy = ProposalWorkPolicy.objects.create(profile=profile, **build_policy(profile))
    snapshot = _knowledge_snapshot(proposal, profile)
    session = GrillSession.objects.create(proposal=proposal, profile=profile, policy=policy, mode=policy.grill_mode, knowledge_snapshot=snapshot)
    if policy.grill_mode == 'skip':
        session.status = 'skipped'
        session.completion_reason = 'skipped'
        session.save(update_fields=['status', 'completion_reason'])
    else:
        for index, (topic, question, blocking, priority) in enumerate(_topics(policy.grill_mode), start=1):
            if index > policy.question_budget:
                break
            GrillDecisionNode.objects.create(
                session=session, node_id=f'{topic}-{index}', topic=topic, question=question,
                question_type='planning_decision', blocking=blocking, priority=priority,
            )
    ProposalDecisionLedger.objects.create(proposal=proposal, session=session, event_type='intake_started', payload={
        'profile_version': profile.version, 'mode': policy.grill_mode, 'user_overrides': profile.user_overrides,
    })
    return session


def next_node(session):
    return session.nodes.filter(status='pending').order_by('priority', 'id').first()


def question_card(node):
    if node is None:
        return None
    return {
        'node_id': node.node_id, 'question': node.question, 'recommended_answer': node.recommended_answer,
        'recommendation_reason': node.recommendation_reason, 'linked_rule_sources': node.rule_evidence_ids,
        'linked_user_evidence': node.user_evidence_ids, 'affected_sections': node.affected_sections,
        'blocking': node.blocking, 'available_actions': ['custom', 'skip', 'end'] + (['adopt_recommendation'] if node.recommended_answer else []),
    }


def _brief_content(session):
    values = {item.topic: item.value for item in session.decisions.all()}
    return {key: values.get(key, '') for key in ('research_object', 'core_problem', 'research_goal', 'research_contents', 'methodology', 'innovation_focus', 'existing_foundation', 'expected_outputs', 'scope_exclusions')}


def refresh_brief(session):
    brief, _ = ProposalBrief.objects.get_or_create(proposal=session.proposal, session=session, defaults={'content': {}})
    brief.content = _brief_content(session)
    brief.save(update_fields=['content', 'updated_at'])
    return brief


@transaction.atomic
def answer_node(session, *, node_id, action, answer, idempotency_key, user=None):
    node = session.nodes.filter(node_id=node_id).first()
    if node is None:
        raise ValueError('node_not_found')
    key = idempotency_key or str(uuid.uuid4())
    prior = GrillAnswer.objects.filter(node=node, idempotency_key=key).first()
    if prior:
        return prior, False
    if node.status != 'pending':
        raise ValueError('node_not_pending')
    if action not in dict(GrillAnswer.ACTION_CHOICES):
        raise ValueError('action_invalid')
    final_answer = node.recommended_answer if action == 'adopt_recommendation' else (answer or '').strip()
    if action in ('custom', 'modify_and_adopt') and not final_answer:
        raise ValueError('answer_required')
    record = GrillAnswer.objects.create(node=node, action=action, answer=final_answer, idempotency_key=key, created_by=user if getattr(user, 'is_authenticated', False) else None)
    if action == 'end':
        session.status = 'user_ended'
        session.completion_reason = 'user_ended'
        session.save(update_fields=['status', 'completion_reason', 'updated_at'])
    elif action == 'skip':
        node.status = 'skipped'
        node.save(update_fields=['status'])
        if session.profile.quality_level == 'quick':
            AssumptionRegister.objects.get_or_create(
                proposal=session.proposal, session=session, assumption=f'{node.topic} 未确认',
                defaults={'risk_level': 'low', 'status': 'open'},
            )
    else:
        decision, created = ProposalDecision.objects.get_or_create(
            node=node,
            defaults={'proposal': session.proposal, 'session': session, 'topic': node.topic, 'value': final_answer, 'affected_sections': node.affected_sections},
        )
        if not created:
            decision.value = final_answer
            decision.version += 1
            decision.save(update_fields=['value', 'version'])
        node.status = 'answered'
        node.save(update_fields=['status'])
        ProposalDecisionLedger.objects.create(proposal=session.proposal, session=session, decision=decision, event_type='decision_confirmed', payload={'topic': node.topic, 'value': final_answer})
    session.question_count += 1
    if session.status == 'active' and not session.nodes.filter(status='pending').exists():
        session.status = 'completed'
        session.completion_reason = 'completed'
    session.save(update_fields=['question_count', 'status', 'completion_reason', 'updated_at'])
    refresh_brief(session)
    return record, True


def consensus(session, *, confirm=False):
    brief = refresh_brief(session)
    blocking_nodes = list(session.nodes.filter(blocking=True).exclude(status__in=['answered', 'auto_resolved']).values_list('node_id', flat=True))
    gaps = list(session.nodes.exclude(status__in=['answered', 'auto_resolved']).values_list('topic', flat=True))
    if confirm:
        if blocking_nodes and session.profile.quality_level != 'quick':
            raise ValueError('blocking_decisions_remaining')
        brief.confirmed = True
        brief.save(update_fields=['confirmed', 'updated_at'])
        ProposalDecisionLedger.objects.create(proposal=session.proposal, session=session, event_type='brief_confirmed', payload={'remaining_gaps': gaps})
    return {
        'proposal_brief': brief.content, 'brief_confirmed': brief.confirmed,
        'decision_ledger': list(session.ledger_entries.order_by('id').values('event_type', 'payload', 'created_at')),
        'assumptions': list(AssumptionRegister.objects.filter(session=session).values('assumption', 'risk_level', 'status')),
        'remaining_gaps': gaps, 'blocking_decisions': blocking_nodes,
    }


def work_plan_preview(session):
    return {
        'grill_mode': session.mode, 'question_budget': session.policy.question_budget,
        'preserve_user_structure': session.policy.preserve_user_structure,
        'knowledge_snapshot': session.knowledge_snapshot,
        'rule_readiness': session.profile.rule_readiness, 'content_maturity': session.profile.content_maturity,
        'evidence_readiness': session.profile.evidence_readiness,
    }
