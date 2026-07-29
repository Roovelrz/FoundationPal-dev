from django.db import transaction
from django.db.models import Q

from proposals.models import ProposalSection

from .models import (
    Claim, ClaimEvidenceBinding, ClaimIntent, ClaimPlan, EvidenceNeed, GrantPackVersion, GrantRequirement,
    ProposalBrief, ProposalDecision, SectionPlan, SectionSchema, UserEvidence,
)


def _planning_mode(brief):
    profile = brief.session.profile
    if profile.task_mode == 'polish_existing' and profile.content_maturity == 'full_draft':
        return 'extract_from_draft'
    if profile.task_mode == 'refine_outline':
        return 'complete' if profile.content_maturity in ('none', 'rough_notes') else 'validate'
    return 'create'


def _claim_type(topic):
    if topic == 'existing_foundation':
        return 'factual'
    if topic in ('budget', 'duration'):
        return 'numerical'
    if topic in ('innovation_focus', 'core_problem'):
        return 'interpretive'
    return 'proposed'


def _requirement_groups(version):
    schemas = list(SectionSchema.objects.filter(pack_version=version).order_by('order', 'id'))
    requirements = list(GrantRequirement.objects.filter(pack_version=version).order_by('priority', 'id'))
    if schemas:
        groups = []
        for schema in schemas:
            selected = [item for item in requirements if schema.id in {value.id for value in item.target_sections.all()}]
            groups.append((schema.section_key, schema.title, schema.order, schema, selected))
        unassigned = [item for item in requirements if not item.target_sections.exists()]
        if unassigned:
            groups[0] = (*groups[0][:4], groups[0][4] + unassigned)
        return groups
    grouped = {}
    for item in requirements:
        grouped.setdefault(item.requirement_type, []).append(item)
    return [(f'rule-{kind}', f'{kind} requirements', index, None, values) for index, (kind, values) in enumerate(sorted(grouped.items()), start=1)]


def _latest_confirmed_brief(proposal):
    return ProposalBrief.objects.filter(proposal=proposal, confirmed=True).select_related('session__profile', 'session__policy').order_by('-version', '-id').first()


@transaction.atomic
def create_claim_plan(proposal, *, pack_version_id):
    brief = _latest_confirmed_brief(proposal)
    if brief is None:
        raise ValueError('confirmed_proposal_brief_required')
    version = GrantPackVersion.objects.filter(pk=pack_version_id, status='published').first()
    if version is None:
        raise ValueError('published_grant_pack_required')
    selected_pack = brief.session.profile.detected_inputs.get('pack_version_id')
    if selected_pack and int(selected_pack) != version.id:
        raise ValueError('grant_pack_version_mismatch')
    policy = brief.session.policy
    plan = ClaimPlan.objects.create(
        proposal=proposal, brief=brief, policy=policy, pack_version=version,
        planning_mode=_planning_mode(brief),
    )
    groups = _requirement_groups(version)
    if not groups:
        raise ValueError('grant_requirements_required')
    all_decisions = list(brief.session.decisions.all().order_by('id'))
    section_plans = []
    for key, title, order, schema, requirements in groups:
        section_plan = SectionPlan.objects.create(claim_plan=plan, section_schema=schema, section_key=key, title=title, order=order)
        section_plan.target_requirements.set(requirements)
        section_plans.append(section_plan)
    for index, decision in enumerate(all_decisions):
        section_plan = section_plans[index % len(section_plans)]
        section_plan.proposal_decisions.add(decision)
        claim_type = _claim_type(decision.topic)
        intent = ClaimIntent.objects.create(
            section_plan=section_plan, proposal_decision=decision, claim_type=claim_type,
            text=decision.value, risk_level='high' if claim_type in ('factual', 'numerical') else 'low',
        )
        requirements = list(section_plan.target_requirements.all())
        intent.addressed_requirements.set(requirements)
        needs = []
        if claim_type in ('factual', 'numerical'):
            has_evidence = UserEvidence.objects.filter(organization_id=str(proposal.org_id)).exists()
            need = EvidenceNeed.objects.create(
                section_plan=section_plan, claim_intent=intent, evidence_type='user_evidence',
                description=f'{decision.topic} requires user evidence', required_for_claim_type=claim_type,
                status='satisfied' if has_evidence else 'open',
            )
            needs.append(need)
        section_plan.claim_intents = list(section_plan.claim_intents or []) + [{'claim_intent_id': intent.id, 'type': claim_type, 'decision_id': decision.id}]
        section_plan.save(update_fields=['claim_intents'])
    mandatory = set(GrantRequirement.objects.filter(pack_version=version, mandatory=True).values_list('id', flat=True))
    covered = set(SectionPlan.objects.filter(claim_plan=plan).values_list('target_requirements__id', flat=True)) - {None}
    plan.requirement_gaps = sorted(mandatory - covered)
    plan.evidence_gaps = list(EvidenceNeed.objects.filter(section_plan__claim_plan=plan, status='open').values_list('id', flat=True))
    plan.save(update_fields=['requirement_gaps', 'evidence_gaps'])
    return plan


def coverage(plan):
    mandatory = set(GrantRequirement.objects.filter(pack_version=plan.pack_version, mandatory=True).values_list('id', flat=True))
    covered = set(plan.section_plans.values_list('target_requirements__id', flat=True)) - {None}
    return {'mandatory_total': len(mandatory), 'mandatory_covered': len(mandatory & covered), 'requirement_gaps': sorted(mandatory - covered)}


@transaction.atomic
def confirm_claim_plan(plan):
    if plan.status == 'confirmed':
        return plan
    if plan.status != 'planned':
        raise ValueError('claim_plan_not_confirmable')
    if plan.requirement_gaps:
        raise ValueError('mandatory_requirement_gaps')
    for section_plan in plan.section_plans.order_by('order', 'id'):
        section, _ = ProposalSection.objects.get_or_create(
            proposal=plan.proposal, key=section_plan.section_key,
            defaults={'title': section_plan.title, 'order': section_plan.order},
        )
        for intent in section_plan.claim_intents_records.all():
            claim, _ = Claim.objects.get_or_create(
                proposal=plan.proposal, proposal_section=section, text=intent.text,
                defaults={
                    'claim_type': intent.claim_type,
                    'status': 'missing_evidence' if intent.evidence_needs.filter(status='open').exists() else 'planned',
                    'source_mode': 'confirmed_brief', 'risk_level': intent.risk_level,
                },
            )
            claim.proposal_decisions.add(intent.proposal_decision)
            claim.addressed_requirements.set(intent.addressed_requirements.all())
            for requirement in intent.addressed_requirements.all():
                ClaimEvidenceBinding.objects.get_or_create(
                    claim=claim, grant_requirement=requirement,
                    defaults={'support_type': 'requirement_addressed', 'support_strength': 'direct', 'reviewer_status': 'pending'},
                )
            if intent.claim_type in ('factual', 'numerical'):
                evidence = UserEvidence.objects.filter(organization_id=str(plan.proposal.org_id)).filter(
                    Q(proposal__isnull=True) | Q(proposal_id=plan.proposal_id)
                ).first()
                if evidence is not None:
                    ClaimEvidenceBinding.objects.get_or_create(
                        claim=claim, user_evidence=evidence,
                        defaults={'support_type': 'factual_support', 'support_strength': 'partial', 'reviewer_status': 'pending'},
                    )
    plan.status = 'confirmed'
    plan.save(update_fields=['status'])
    return plan


@transaction.atomic
def invalidate_for_decision(decision: ProposalDecision):
    plans = ClaimPlan.objects.filter(section_plans__proposal_decisions=decision).distinct()
    plans.update(status='needs_replan')
    Claim.objects.filter(proposal_decisions=decision).exclude(status='locked').update(status='outdated')


def serialize_claim_plan(plan):
    return {
        'claim_plan_id': plan.id, 'status': plan.status, 'planning_mode': plan.planning_mode,
        'pack_version_id': plan.pack_version_id, 'coverage': coverage(plan), 'evidence_gaps': plan.evidence_gaps,
        'section_plans': [
            {
                'section_key': item.section_key, 'title': item.title,
                'requirement_ids': list(item.target_requirements.values_list('id', flat=True)),
                'proposal_decision_ids': list(item.proposal_decisions.values_list('id', flat=True)),
                'claim_intents': list(item.claim_intents_records.values('id', 'claim_type', 'text', 'proposal_decision_id')),
                'evidence_needs': list(item.evidence_needs.values('id', 'evidence_type', 'status')),
            } for item in plan.section_plans.order_by('order', 'id')
        ],
    }
