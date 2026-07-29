import re

from django.db import transaction

from .claim_planning import _latest_confirmed_brief
from .diff_engine import diff_texts
from .intake import answer_node, next_node, question_card
from .models import (
    Claim, ClaimLedgerEntry, ClaimSentenceMapping, EvidenceFact, GrillDecisionNode, GrillSession, ProposalDecision,
    ReviewDecision, ReviewIssue, ReviewRevision, SectionPlan, SectionWriterRun,
)
from .services import ServiceError, revise_service
from .writer_evidence import render_writer_contexts, retrieve_writer_evidence


WRITING_MODE_BY_PLAN = {
    'create': 'generate', 'complete': 'continue', 'validate': 'audit_and_polish',
    'extract_from_draft': 'audit_and_polish',
}

IMPLEMENTED_REVIEW_CODES = {
    'mandatory_requirement_gap', 'word_limit_exceeded', 'missing_claim_evidence', 'unsupported_claim',
    'duplicate_claim', 'numerical_conflict', 'completion_status_conflict', 'missing_attachment_evidence',
    'missing_budget_decision', 'human_decision_preserved',
    'locked_claim_change_attempt', 'duplicate_funding_conflict', 'role_attribution_conflict',
    'metric_definition_conflict', 'cross_section_consistency', 'overclaiming',
}

REVIEW_POLICIES = {
    code: {'allowed_actions': {'custom', 'modify_and_adopt', 'end'}, 'forbidden_actions': {'close'}, 'required_material': 'evidence_or_human_decision', 'locked_claim_restricted': True, 'requires_reverification': True, 'can_close_directly': False}
    for code in IMPLEMENTED_REVIEW_CODES
}


def _numbers(value):
    values = []
    for item in re.findall(r'\d+(?:\.\d+)?', value or ''):
        normalized = item.rstrip('0').rstrip('.') if '.' in item else item
        values.append(normalized or '0')
    return values


def refresh_claim_ledger(claim):
    evidence_ids = list(claim.evidence_bindings.exclude(user_evidence__isnull=True).values_list('user_evidence_id', flat=True))
    facts = list(EvidenceFact.objects.filter(user_evidence_id__in=evidence_ids).exclude(verification_status__in=['rejected', 'conflicted']))
    ledger = {
        'claim_id': claim.id,
        'section_key': claim.proposal_section.key if claim.proposal_section_id else '',
        'claim_type': claim.claim_type,
        'normalized_values': _numbers(claim.text),
        'evidence_fact_ids': [fact.id for fact in facts],
        'evidence_numeric_values': [_numbers(str(fact.numeric_value))[0] for fact in facts if fact.numeric_value is not None],
        'time_scopes': [fact.time_range for fact in facts if fact.time_range],
        'completion_statuses': sorted({fact.fact_status for fact in facts}),
        'roles': sorted({fact.user_role for fact in facts if fact.user_role != 'unknown'}),
        'proposal_decision_ids': list(claim.proposal_decisions.values_list('id', flat=True)),
        'lock_state': claim.status in {'locked', 'human_approved'},
    }
    if claim.ledger != ledger:
        claim.ledger = ledger
        claim.save(update_fields=['ledger'])
    ClaimLedgerEntry.objects.filter(claim=claim).delete()
    decisions = list(claim.proposal_decisions.all()) or [None]
    for fact in facts or [None]:
        for decision in decisions:
            ClaimLedgerEntry.objects.create(
                claim=claim, evidence_fact=fact, proposal_decision=decision,
                subject=fact.subject if fact else '', predicate=fact.predicate if fact else '', object=fact.object if fact else '',
                numeric_value=fact.numeric_value if fact else None, unit=fact.unit if fact else '', metric_definition=fact.metric_definition if fact else '',
                time_range=fact.time_range if fact else {}, completion_status=fact.project_status or fact.fact_status if fact else '',
                person_role=fact.user_role if fact else '', funding_source=decision.value if decision and ('预算' in decision.topic or '经费' in decision.topic) else '',
                locked=claim.status in {'locked', 'human_approved'},
            )
    return ledger


def _claim_asserts_completed(text):
    return any(value in (text or '') for value in ('已完成', '已结题', '已经结题', '完成了'))


def _find_section_plan(section):
    return SectionPlan.objects.filter(claim_plan__proposal=section.proposal, claim_plan__status='confirmed', section_key=section.key).select_related('claim_plan__brief', 'claim_plan__policy', 'claim_plan__pack_version').order_by('-id').first()


def prepare_writer_run(section):
    section_plan = _find_section_plan(section)
    if section_plan is None:
        raise ValueError('confirmed_section_plan_required')
    claim_plan = section_plan.claim_plan
    contexts = retrieve_writer_evidence(
        section.key,
        {'_pack_version_id': str(claim_plan.pack_version_id), '_year': str(claim_plan.pack_version.year)},
        organization_id=str(section.proposal.org_id), proposal_id=section.proposal_id,
    )
    rule_context, evidence_context = render_writer_contexts(contexts)
    protected = list(Claim.objects.filter(proposal_section=section, status__in=['locked', 'human_approved']).values_list('text', flat=True))
    missing = list(Claim.objects.filter(proposal_section=section, status='missing_evidence').values_list('text', flat=True))
    run = SectionWriterRun.objects.create(
        section=section, section_plan=section_plan,
        writing_mode=WRITING_MODE_BY_PLAN[claim_plan.planning_mode],
        rule_context=[item['chunk_id'] for item in contexts.rule_candidates],
        user_evidence_context=[item['chunk_id'] for item in contexts.user_evidence_candidates],
        protected_facts=protected, missing_evidence=missing,
        proposal_brief=claim_plan.brief.content,
        work_policy={'quality_level': claim_plan.brief.session.profile.quality_level, 'preserve_user_structure': claim_plan.policy.preserve_user_structure},
    )
    return run, rule_context, evidence_context


def record_claim_mappings(section, draft_text):
    ClaimSentenceMapping.objects.filter(section=section).delete()
    mappings = []
    for claim in Claim.objects.filter(proposal_section=section):
        start = draft_text.find(claim.text)
        if start >= 0:
            mappings.append(ClaimSentenceMapping.objects.create(
                claim=claim, section=section, start_offset=start, end_offset=start + len(claim.text), text_snapshot=claim.text,
            ))
    return mappings


def _issue(section, *, claim=None, requirement=None, category, code, message, severity, auto_fixable=False):
    issue = ReviewIssue.objects.filter(section=section, claim=claim, requirement=requirement, code=code, status__in=['open', 'needs_user_decision']).first()
    if issue is None:
        issue = ReviewIssue.objects.create(
            proposal=section.proposal, section=section, claim=claim, requirement=requirement,
            category=category, code=code, message=message, severity=severity, auto_fixable=auto_fixable,
        )
    return issue


@transaction.atomic
def run_review(section):
    section_plan = _find_section_plan(section)
    if section_plan is None:
        raise ValueError('confirmed_section_plan_required')
    quality = section_plan.claim_plan.brief.session.profile.quality_level
    issues = []
    claims = list(Claim.objects.filter(proposal_section=section))
    addressed = set()
    for claim in claims:
        addressed.update(claim.addressed_requirements.values_list('id', flat=True))
    for requirement in section_plan.target_requirements.filter(mandatory=True):
        if requirement.id not in addressed:
            issues.append(_issue(section, requirement=requirement, category='rule', code='mandatory_requirement_gap', message='Mandatory requirement is not addressed by a claim.', severity='high'))
    schema = section_plan.section_schema
    if schema and schema.word_limit:
        count = len((section.draft_content or '').split())
        if count > schema.word_limit:
            issues.append(_issue(section, category='rule', code='word_limit_exceeded', message='Section exceeds the configured word limit.', severity='low', auto_fixable=True))
    for claim in claims:
        ledger = refresh_claim_ledger(claim)
        if claim.claim_type in ('factual', 'numerical') and not claim.evidence_bindings.filter(user_evidence__isnull=False).exists():
            issues.append(_issue(section, claim=claim, category='fact', code='missing_claim_evidence', message='Factual or numerical claim lacks user evidence.', severity='high'))
        if claim.claim_type == 'unsupported':
            issues.append(_issue(section, claim=claim, category='fact', code='unsupported_claim', message='Claim is marked unsupported.', severity='high'))
        if claim.status == 'locked' and claim.ledger.get('locked_text') and claim.ledger['locked_text'] != claim.text:
            issues.append(_issue(section, claim=claim, category='fact', code='locked_claim_change_attempt', message='Locked claim text was changed.', severity='high'))
        fact_text = ' '.join(f'{fact.object} {fact.predicate}' for fact in EvidenceFact.objects.filter(pk__in=ledger['evidence_fact_ids']))
        if '重复资助' in claim.text and ('无重复资助' in fact_text or 'no_duplicate_funding' in fact_text):
            issues.append(_issue(section, claim=claim, category='fact', code='duplicate_funding_conflict', message='Claim conflicts with verified no-duplicate-funding evidence.', severity='high'))
        if ledger['roles'] and '申请人负责' in claim.text and all(role not in {'lead', 'unknown'} for role in ledger['roles']):
            issues.append(_issue(section, claim=claim, category='fact', code='role_attribution_conflict', message='Claim attributes work to applicant despite bound evidence role.', severity='high'))
        definitions = set(EvidenceFact.objects.filter(pk__in=ledger['evidence_fact_ids']).exclude(metric_definition='').values_list('metric_definition', flat=True))
        if len(definitions) > 1:
            issues.append(_issue(section, claim=claim, category='fact', code='metric_definition_conflict', message='Bound evidence has conflicting metric definitions.', severity='high'))
        if any(term in claim.text for term in ('全部', '均超过', '完全')) and not ledger['evidence_fact_ids']:
            issues.append(_issue(section, claim=claim, category='fact', code='overclaiming', message='Absolute claim lacks bound evidence.', severity='high'))
        if claim.claim_type == 'numerical' and ledger['evidence_numeric_values']:
            claim_values = set(ledger['normalized_values'])
            fact_values = set(ledger['evidence_numeric_values'])
            if claim_values and not claim_values.intersection(fact_values):
                issues.append(_issue(section, claim=claim, category='fact', code='numerical_conflict', message='Claim numeric value conflicts with bound evidence facts.', severity='high'))
        if _claim_asserts_completed(claim.text) and ledger['completion_statuses'] and not {'completed'}.intersection(ledger['completion_statuses']):
            issues.append(_issue(section, claim=claim, category='fact', code='completion_status_conflict', message='Claim asserts completion but bound evidence is not completed.', severity='high'))
        if ('附件' in claim.text or '附表' in claim.text) and not ledger['evidence_fact_ids']:
            issues.append(_issue(section, claim=claim, category='fact', code='missing_attachment_evidence', message='Claim references an attachment without verified evidence facts.', severity='high'))
        if ('预算' in claim.text or '经费' in claim.text) and not claim.proposal_decisions.filter(topic__icontains='预算').exists() and not claim.proposal_decisions.filter(topic__icontains='经费').exists():
            issues.append(_issue(section, claim=claim, category='cross_system', code='missing_budget_decision', message='Budget or funding claim lacks a linked human decision.', severity='high'))
        for decision in claim.proposal_decisions.all():
            if decision.value and decision.value not in claim.text:
                issues.append(_issue(section, claim=claim, category='cross_system', code='human_decision_preserved', message='Claim no longer preserves its linked human decision.', severity='high'))
    if quality != 'quick':
        duplicates = Claim.objects.filter(proposal=section.proposal, text__in=[item.text for item in claims]).exclude(proposal_section=section)
        if duplicates.exists():
            issues.append(_issue(section, category='cross_system', code='duplicate_claim', message='A claim is repeated in another section.', severity='low'))
        values = {claim.text: claim for claim in claims}
        conflicts = Claim.objects.filter(proposal=section.proposal).exclude(proposal_section=section).exclude(text__in=values)
        if any(set(_numbers(claim.text)) & set(_numbers(other.text)) == set() for claim in claims for other in conflicts if _numbers(claim.text) and _numbers(other.text)):
            issues.append(_issue(section, category='cross_system', code='cross_section_consistency', message='Numeric claims conflict across sections.', severity='high'))
    for issue in issues:
        if issue.severity == 'high':
            issue.status = 'needs_user_decision'
            issue.save(update_fields=['status'])
    active_ids = {issue.id for issue in issues}
    stale = ReviewIssue.objects.filter(section=section, code__in=IMPLEMENTED_REVIEW_CODES, status__in=['open', 'needs_user_decision']).exclude(id__in=active_ids)
    stale.update(status='resolved')
    return issues


@transaction.atomic
def start_review_grill(section):
    section_plan = _find_section_plan(section)
    if section_plan is None:
        raise ValueError('confirmed_section_plan_required')
    issues = section.review_issues.filter(status='needs_user_decision', review_decision__isnull=True).order_by('id')
    if section_plan.claim_plan.brief.session.profile.quality_level == 'quick':
        issues = issues.filter(severity='high')
    session = GrillSession.objects.create(
        proposal=section.proposal, profile=section_plan.claim_plan.brief.session.profile,
        policy=section_plan.claim_plan.policy, mode='review', knowledge_snapshot={'review_issue_ids': list(issues.values_list('id', flat=True))},
    )
    for index, issue in enumerate(issues, start=1):
        GrillDecisionNode.objects.create(
            session=session, node_id=f'review-{issue.id}', topic=f'review_issue_{issue.id}',
            question=issue.message, question_type='review_decision', blocking=issue.severity == 'high', priority=index,
            affected_sections=[section.key],
        )
    return session


@transaction.atomic
def answer_review_grill(session, *, node_id, action, answer, idempotency_key, user=None):
    issue_id = int(node_id.removeprefix('review-'))
    issue = ReviewIssue.objects.get(pk=issue_id)
    if ReviewDecision.objects.filter(issue=issue).exists():
        raise ValueError('review_issue_already_decided')
    record, created = answer_node(session, node_id=node_id, action=action, answer=answer, idempotency_key=idempotency_key, user=user)
    if not created:
        return record, False
    if action not in REVIEW_POLICIES.get(issue.code, {'allowed_actions': {'custom'}})['allowed_actions']:
        raise ValueError('review_action_not_allowed')
    decision = ProposalDecision.objects.get(node=record.node)
    ReviewDecision.objects.create(issue=issue, session=session, decision=decision, action=action)
    issue.status = 'needs_user_decision'
    issue.save(update_fields=['status'])
    return record, True


@transaction.atomic
def reverify_review_grill(session, *, issue_id):
    issue = ReviewIssue.objects.select_related('section').get(pk=issue_id, proposal=session.proposal)
    run_review(issue.section)
    issue.refresh_from_db()
    return issue.status == 'resolved'


@transaction.atomic
def apply_local_revision(section, *, revised_text, issue=None, user_id=None):
    if section.locked:
        raise ServiceError('section_locked')
    protected = list(Claim.objects.filter(proposal_section=section, status__in=['locked', 'human_approved']).values_list('text', flat=True))
    if any(value not in revised_text for value in protected):
        raise ValueError('protected_fact_modified')
    before = section.draft_content or ''
    diff = diff_texts(before, revised_text)
    revise_service(section=section, revised_text=revised_text, user_id=user_id, from_text=before, diff=diff)
    ReviewRevision.objects.create(section=section, issue=issue, trigger=issue.code if issue else 'manual', before_text=before, after_text=revised_text, diff=diff)
    if issue and issue.auto_fixable:
        issue.status = 'auto_fixed'
        issue.save(update_fields=['status'])
    record_claim_mappings(section, revised_text)
    return diff
