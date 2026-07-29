from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    Claim,
    ClaimEvidenceBinding,
    EvidenceAuthorization,
    EvidenceFact,
    EvidenceVerification,
    GrantPackVersion,
    GrantPack,
    GrantProgram,
    GrantRequirement,
    RuleConflict,
    UserEvidence,
    AIResource,
)
from .rule_pack_compiler import bind_rule_pack_documents


@transaction.atomic
def create_custom_pack_draft(proposal, payload):
    resource_ids = payload.get('resource_ids') or []
    if not isinstance(resource_ids, list) or not resource_ids:
        raise ValueError('rule_pack_resource_ids_required')
    resources = list(AIResource.objects.filter(id__in=resource_ids, knowledge_domain='grant_rule', is_deleted=False))
    if len(resources) != len(set(resource_ids)):
        raise ValueError('rule_pack_resource_not_found')
    if any(item.organization_id and item.organization_id != str(proposal.org_id) for item in resources):
        raise ValueError('rule_pack_resource_forbidden')
    name = str(payload.get('name') or '自定义基金规则包').strip()[:256]
    year = int(payload.get('year') or timezone.now().year)
    program_type = str(payload.get('program_type') or 'custom')[:128]
    program, _ = GrantProgram.objects.get_or_create(name=name, program_type=program_type, region='', defaults={'authority': 'organization'})
    code = f'custom-{proposal.org_id}-{timezone.now().strftime("%Y%m%d%H%M%S%f")}'
    pack = GrantPack.objects.create(program=program, code=code, name=name, organization_id=str(proposal.org_id), is_public=False)
    version = GrantPackVersion.objects.create(pack=pack, year=year, version='draft-1', status='draft')
    bind_rule_pack_documents(pack_version=version, resources=resources)
    return {'pack_id': pack.id, 'pack_version_id': version.id, 'status': version.status, 'resource_ids': [item.id for item in resources]}


def serialize_pack_review(version):
    requirements = list(version.requirements.select_related('source_chunk').order_by('priority', 'id'))
    conflicts = list(version.conflicts.select_related('primary_requirement', 'conflicting_requirement').order_by('id'))
    return {
        'pack_version_id': version.id,
        'pack_name': version.pack.name,
        'year': version.year,
        'version': version.version,
        'status': version.status,
        'unreviewed_document_count': version.documents.filter(needs_human_review=True).count(),
        'requirements': [
            {
                'id': item.id,
                'text': item.text,
                'requirement_type': item.requirement_type,
                'mandatory': item.mandatory,
                'applicability': item.applicability,
                'source_chunk_id': item.source_chunk_id,
                'source_excerpt': item.source_excerpt,
            }
            for item in requirements
        ],
        'conflicts': [
            {
                'id': item.id,
                'description': item.description,
                'human_resolution': item.human_resolution,
                'primary_requirement_id': item.primary_requirement_id,
                'conflicting_requirement_id': item.conflicting_requirement_id,
            }
            for item in conflicts
        ],
    }


def update_pack_review(version, payload, reviewer):
    action = payload.get('action')
    if action == 'update_requirement':
        requirement = version.requirements.filter(pk=payload.get('requirement_id')).first()
        if requirement is None:
            raise ValueError('requirement_not_found')
        allowed = {'requirement_type', 'mandatory', 'applicability', 'text', 'applicable_condition'}
        changed = []
        for field in allowed:
            if field in payload:
                setattr(requirement, field, payload[field])
                changed.append(field)
        if not changed:
            raise ValueError('requirement_update_empty')
        requirement.full_clean()
        requirement.save(update_fields=changed)
    elif action == 'resolve_conflict':
        conflict = version.conflicts.filter(pk=payload.get('conflict_id')).first()
        resolution = str(payload.get('resolution') or '').strip()
        if conflict is None:
            raise ValueError('conflict_not_found')
        if not resolution:
            raise ValueError('conflict_resolution_required')
        conflict.human_resolution = resolution
        conflict.reviewer = reviewer if getattr(reviewer, 'is_authenticated', False) else None
        conflict.save(update_fields=['human_resolution', 'reviewer'])
    elif action == 'publish':
        if version.status not in {'validated', 'published'}:
            raise ValueError('pack_not_validated')
        if version.documents.filter(needs_human_review=True).exists():
            raise ValueError('pack_has_unreviewed_documents')
        if version.conflicts.filter(human_resolution='').exists():
            raise ValueError('pack_has_unresolved_conflicts')
        version.status = 'published'
        version.save(update_fields=['status'])
    else:
        raise ValueError('pack_review_action_invalid')
    return serialize_pack_review(version)


def serialize_evidence_review(proposal):
    evidence = UserEvidence.objects.filter(
        Q(proposal=proposal) | Q(organization_id=str(proposal.org_id), proposal__isnull=True)
    ).select_related('resource', 'chunk').prefetch_related('facts').order_by('id')
    items = []
    for item in evidence:
        items.append({
            'user_evidence_id': item.id,
            'resource_id': item.resource_id,
            'chunk_id': item.chunk_id,
            'authorization_scope': item.authorization_scope,
            'facts': [{
                'id': fact.id,
                'subject': fact.subject,
                'predicate': fact.predicate,
                'object': fact.object,
                'fact_status': fact.fact_status,
                'user_role': fact.user_role,
                'numeric_value': str(fact.numeric_value) if fact.numeric_value is not None else None,
                'verification_status': fact.verification_status,
            } for fact in item.facts.all()],
        })
    return {'proposal_id': proposal.id, 'evidence': items}


@transaction.atomic
def update_evidence_review(proposal, payload, reviewer):
    fact = EvidenceFact.objects.select_related('user_evidence').filter(pk=payload.get('fact_id')).first()
    if fact is None or fact.user_evidence.proposal_id not in {None, proposal.id} or fact.user_evidence.organization_id != str(proposal.org_id):
        raise ValueError('evidence_fact_not_found')
    action = payload.get('action')
    if action == 'verify_fact':
        status = payload.get('verification_status')
        if status not in dict(EvidenceFact.VERIFICATION_STATUS_CHOICES):
            raise ValueError('verification_status_invalid')
        fields = ['verification_status']
        fact.verification_status = status
        for field in ('fact_status', 'user_role'):
            if field in payload:
                choices = dict(getattr(EvidenceFact, f'{field.upper()}_CHOICES'))
                if payload[field] not in choices:
                    raise ValueError(f'{field}_invalid')
                setattr(fact, field, payload[field])
                fields.append(field)
        fact.save(update_fields=fields)
        EvidenceVerification.objects.create(fact=fact, reviewer=reviewer if getattr(reviewer, 'is_authenticated', False) else None, status=status, note=str(payload.get('note') or ''))
    elif action == 'set_scope':
        scope = payload.get('authorization_scope')
        if scope not in {'organization', 'proposal', 'private'}:
            raise ValueError('authorization_scope_invalid')
        record = fact.user_evidence
        record.authorization_scope = scope
        if scope == 'proposal':
            record.proposal = proposal
        record.save(update_fields=['authorization_scope', 'proposal'])
    elif action == 'revoke':
        EvidenceAuthorization.objects.create(user_evidence=fact.user_evidence, proposal=proposal, owner_user=reviewer if getattr(reviewer, 'is_authenticated', False) else None, allowed=False)
        ClaimEvidenceBinding.objects.filter(user_evidence=fact.user_evidence, claim__proposal=proposal).update(reviewer_status='revoked')
        Claim.objects.filter(proposal=proposal, evidence_bindings__user_evidence=fact.user_evidence).exclude(status='locked').update(status='missing_evidence')
    else:
        raise ValueError('evidence_review_action_invalid')
    return serialize_evidence_review(proposal)


def decide_claim(proposal, payload):
    claim = proposal.claims.filter(pk=payload.get('claim_id')).first()
    if claim is None:
        raise ValueError('claim_not_found')
    action = payload.get('action')
    if action == 'lock':
        claim.status = 'locked'
        claim.save(update_fields=['status'])
    elif action == 'reject':
        claim.status = 'rejected'
        claim.save(update_fields=['status'])
    elif action == 'narrow':
        text = str(payload.get('text') or '').strip()
        if not text:
            raise ValueError('claim_text_required')
        claim.text = text
        claim.status = 'drafted'
        claim.save(update_fields=['text', 'status'])
    elif action == 'replace_evidence':
        evidence_id = payload.get('user_evidence_id')
        evidence = UserEvidence.objects.filter(pk=evidence_id).filter(
            Q(proposal=proposal) | Q(organization_id=str(proposal.org_id), proposal__isnull=True)
        ).first()
        if evidence is None:
            raise ValueError('user_evidence_not_found')
        ClaimEvidenceBinding.objects.filter(claim=claim, user_evidence__isnull=False).delete()
        ClaimEvidenceBinding.objects.create(claim=claim, user_evidence=evidence, support_type='support', support_strength='human_confirmed', reviewer_status='accepted')
        claim.status = 'human_approved'
        claim.save(update_fields=['status'])
    else:
        raise ValueError('claim_decision_action_invalid')
    return {'claim_id': claim.id, 'status': claim.status, 'text': claim.text}
