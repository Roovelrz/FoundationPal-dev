import re
import uuid
from dataclasses import dataclass

from django.db.models import Q

from .embedding_service import embed_texts
from .domain_indexing import query_embedding_input
from .models import EvidenceAuthorization, EvidenceFact, GrantPackVersion, GrantRequirement, RuleConflict, UserEvidence
from .retrieval import _cosine


def _terms(value: str) -> set[str]:
    normalized = value.lower().replace('－', '-').replace('—', '-')
    tokens = {item for item in re.split(r'[^0-9a-zA-Z_]+', normalized) if item}
    chinese = ''.join(re.findall(r'[\u4e00-\u9fff]', normalized))
    for width in (2, 3):
        tokens.update(chinese[index:index + width] for index in range(len(chinese) - width + 1))
    tokens.update(f'number:{item}' for item in re.findall(r'\d+(?:\.\d+)?', normalized))
    tokens.update(f'rule:{item.lower()}' for item in re.findall(r'(?:附件|第)?\s*\d+(?:\.\d+)+(?:条|项)?', normalized))
    return tokens


def _overlap_score(query_terms: set[str], text: str) -> int:
    return len(query_terms & _terms(text))


def _atomic_rule_is_usable(requirement: GrantRequirement) -> bool:
    meaningful = re.sub(r'[\d\s\W_]+', '', requirement.text or '')
    return len(meaningful) >= 4


def _atomic_rule_context(requirement: GrantRequirement) -> dict:
    chunk = requirement.source_chunk
    neighbors = chunk.resource.chunks.filter(chunk_index__in=[chunk.chunk_index - 1, chunk.chunk_index + 1]).order_by('chunk_index')
    return {
        'rule_text': requirement.text,
        'condition': requirement.applicable_condition,
        'parent_section': chunk.section_title,
        'parent_chunk_id': chunk.parent_chunk_id,
        'source_page_start': chunk.page_start,
        'source_page_end': chunk.page_end,
        'neighbor_chunk_ids': list(neighbors.values_list('id', flat=True)),
        'source_file_name': (chunk.resource.metadata or {}).get('source_file_name', chunk.resource.display_name),
        'source_file_sha256': (chunk.resource.metadata or {}).get('source_file_sha256', chunk.resource.sha256),
        'source_url': (chunk.resource.metadata or {}).get('source_url', chunk.resource.source_url),
    }


def _rule_ranking_factors(requirement: GrantRequirement, query_terms: set[str], query: 'RuleQuery', applicability_status: str) -> dict:
    title = ' '.join(filter(None, [
        requirement.source_chunk.section_title,
        requirement.source_chunk.resource.display_name,
        requirement.source_chunk.rule_number,
    ]))
    metadata = requirement.source_chunk.resource.metadata or {}
    source_complete = int(bool(
        metadata.get('source_file_name', requirement.source_chunk.resource.display_name)
        and metadata.get('source_file_sha256', requirement.source_chunk.resource.sha256)
        and requirement.source_chunk.page_start
        and (requirement.source_excerpt or requirement.text)
    ))
    return {
        'title_match': _overlap_score(query_terms, title),
        'applicability_match': {'applicable': 2, 'insufficient_information': 1}.get(applicability_status, 0),
        'source_traceability': source_complete,
    }


def _applicability_status(requirement: GrantRequirement, query: 'RuleQuery') -> str:
    scope = requirement.applicability or {}
    facts = {
        'program_type': query.program_type,
        'program_category': query.program_category,
        'year': str(query.year or ''),
        'region': query.region,
        'section_key': query.section_key,
        'joint_application': query.joint_application,
        'out_of_province_affiliation': query.out_of_province_affiliation,
        'ethics_or_technology_safety': query.ethics_or_technology_safety,
        'ethics_or_human_genetic_resource': query.ethics_or_human_genetic_resource,
        'completion_review': query.completion_review,
    }
    missing = False
    for key, actual in facts.items():
        expected = scope.get(key)
        if expected in (None, '', [], {}):
            continue
        values = expected if isinstance(expected, list) else [expected]
        if actual in (None, ''):
            missing = True
        elif str(actual) not in {str(value) for value in values}:
            return 'not_applicable'
    return 'insufficient_information' if missing else 'applicable'


def _time_matches(fact: EvidenceFact, requested: dict | None) -> bool:
    if not requested:
        return True
    actual = fact.time_range or {}
    start = str(requested.get('start') or requested.get('year') or '')
    end = str(requested.get('end') or requested.get('year') or '')
    if not start and not end:
        return True
    values = ' '.join(str(value) for value in actual.values())
    if not values:
        return False
    return (not start or start in values) and (not end or end in values)


def _rrf(dense: list[tuple[float, object]], lexical: list[tuple[float, object]], limit: int) -> list[tuple[float, object]]:
    scores = {}
    objects = {}
    for rank, (_, value) in enumerate(dense, start=1):
        scores[value.id] = scores.get(value.id, 0) + 1 / (60 + rank)
        objects[value.id] = value
    for rank, (_, value) in enumerate(lexical, start=1):
        scores[value.id] = scores.get(value.id, 0) + 1 / (60 + rank)
        objects[value.id] = value
    return sorted(((score, objects[key]) for key, score in scores.items()), key=lambda item: (-item[0], item[1].id))[:limit]


@dataclass(frozen=True)
class RuleQuery:
    pack_version_id: int | None
    program_type: str = ''
    program_category: str = ''
    year: int | None = None
    region: str = ''
    section_key: str = ''
    requirement_type: str = ''
    joint_application: bool | None = None
    out_of_province_affiliation: bool | None = None
    ethics_or_technology_safety: bool | None = None
    ethics_or_human_genetic_resource: bool | None = None
    completion_review: bool | None = None
    user_question: str = ''

    def validate(self):
        if not self.pack_version_id:
            raise ValueError('grant_pack_required')


@dataclass(frozen=True)
class EvidenceQuery:
    organization_id: str
    proposal_id: int | None = None
    owner_id: int | None = None
    section_key: str = ''
    claim_intent: str = ''
    evidence_types: tuple[str, ...] = ()
    time_range: dict | None = None
    user_question: str = ''

    def validate(self):
        if not self.organization_id:
            raise ValueError('organization_required')


def rewrite_rule_query(query: RuleQuery) -> list[str]:
    query.validate()
    facts = [
        query.program_type, query.program_category, str(query.year or ''), query.region,
        query.section_key, query.requirement_type,
        *[key for key, value in {
            'joint_application': query.joint_application,
            'out_of_province_affiliation': query.out_of_province_affiliation,
            'ethics_or_technology_safety': query.ethics_or_technology_safety,
            'ethics_or_human_genetic_resource': query.ethics_or_human_genetic_resource,
            'completion_review': query.completion_review,
        }.items() if value is True],
        query.user_question,
    ]
    base = ' '.join(filter(None, facts))
    return [base][:3]


def rewrite_evidence_query(query: EvidenceQuery) -> list[str]:
    query.validate()
    base = ' '.join(filter(None, [query.section_key, query.claim_intent, ' '.join(query.evidence_types), query.user_question]))
    return [base][:5]


class RuleRAGService:
    def search(self, query: RuleQuery) -> dict:
        query.validate()
        version = GrantPackVersion.objects.select_related('pack__program').filter(pk=query.pack_version_id).first()
        if version is None:
            return {'status': 'grant_pack_required', 'results': [], 'audit_candidates': []}
        if version.status != 'published':
            return {'status': 'grant_pack_not_published', 'results': [], 'audit_candidates': []}
        requirements = GrantRequirement.objects.filter(pack_version=version).select_related('source_chunk__resource', 'source_chunk__parent_chunk').prefetch_related('target_sections')
        filter_counts = {'pack_requirements': requirements.count()}
        applied_filters = {'pack_version_id': version.id}
        if query.requirement_type:
            requirements = requirements.filter(requirement_type=query.requirement_type)
            applied_filters['requirement_type'] = query.requirement_type
        filter_counts['after_requirement_type'] = requirements.count()
        if query.section_key:
            section_requirements = requirements.filter(target_sections__section_key=query.section_key).distinct()
            if section_requirements.exists():
                requirements = section_requirements
                applied_filters['section_key'] = query.section_key
        filter_counts['after_section_key'] = requirements.count()
        text = ' '.join(rewrite_rule_query(query)).strip()
        terms = _terms(text)
        vector = embed_texts([query_embedding_input(knowledge_domain='grant_rule', text=text)])[0] if text else []
        applicability = {item.id: _applicability_status(item, query) for item in requirements}
        eligible = [item for item in requirements if applicability[item.id] != 'not_applicable' and _atomic_rule_is_usable(item)]
        filter_counts['after_applicability'] = len(eligible)
        if not eligible:
            return {
                'status': 'no_applicable_rule', 'results': [], 'audit_candidates': [],
                'applied_filters': applied_filters, 'filter_counts': filter_counts,
                'retrieval_query': text, 'retrieval_run_id': str(uuid.uuid4()),
            }
        dense = sorted(((_cosine(vector, item.source_chunk.embedding or []) if vector and item.source_chunk.embedding else 0.0, item) for item in eligible), key=lambda item: (-item[0], item[1].id))[:40]
        lexical = sorted(((_overlap_score(terms, f'{item.text} {item.source_chunk.rule_number} {item.applicable_condition}'), item) for item in eligible), key=lambda item: (-item[0], item[1].id))[:40]
        candidates = _rrf(dense, lexical, 40)
        conflicts = {conflict.primary_requirement_id for conflict in RuleConflict.objects.filter(pack_version=version, human_resolution='')} | {conflict.conflicting_requirement_id for conflict in RuleConflict.objects.filter(pack_version=version, human_resolution='')}
        results = []
        ranked = []
        for score, item in candidates:
            lexical_score = _overlap_score(terms, f'{item.text} {item.source_chunk.rule_number} {item.applicable_condition}')
            number_score = len({term for term in terms if term.startswith('number:')} & _terms(f'{item.text} {item.source_chunk.rule_number}'))
            section_score = int(bool(query.section_key and query.section_key in [section.section_key for section in item.target_sections.all()]))
            factors = _rule_ranking_factors(item, terms, query, applicability[item.id])
            final_score = (
                score
                + lexical_score * 0.002
                + number_score * 0.01
                + section_score * 0.01
                + factors['title_match'] * 0.003
                + factors['applicability_match'] * 0.004
                + factors['source_traceability'] * 0.002
            )
            ranked.append((final_score, score, lexical_score, number_score, section_score, factors, item))
        ranked.sort(key=lambda item: (-item[0], item[-1].id))
        for final_score, base_score, lexical_score, number_score, section_score, factors, item in ranked[:5]:
            results.append({
                'requirement_id': item.id, 'chunk_id': item.source_chunk_id,
                'source_document': item.source_chunk.resource.display_name,
                'page_number': item.source_chunk.page_start,
                'original_text': item.source_excerpt or item.text,
                'applicable_scope': item.applicability,
                'authority_level': item.priority,
                'pack_version': version.id,
                'applicability_status': applicability[item.id],
                'atomic_rule': _atomic_rule_context(item),
                'conflict_status': 'unresolved' if item.id in conflicts else 'clear',
                'retrieval_score': round(final_score, 6),
                'ranking_factors': {
                    'rrf': round(base_score, 6), 'lexical_overlap': lexical_score,
                    'number_match': number_score, 'section_match': section_score,
                    **factors,
                },
            })
        missing_application_facts = sorted({
            key for item in eligible if applicability[item.id] == 'insufficient_information'
            for key, expected in (item.applicability or {}).items()
            if key in {'program_type', 'program_category', 'year', 'region', 'section_key', 'joint_application', 'out_of_province_affiliation', 'ethics_or_technology_safety', 'ethics_or_human_genetic_resource', 'completion_review'}
            and expected not in (None, '', [], {}) and getattr(query, key, None) in (None, '')
        })
        status = 'human_review_required' if results and all(item['conflict_status'] == 'unresolved' for item in results) else ('insufficient_information' if results and all(item['applicability_status'] == 'insufficient_information' for item in results) else ('ok' if results else 'no_applicable_rule'))
        return {
            'status': status,
            'results': results,
            'audit_candidates': [item.id for _, item in candidates],
            'audit_candidate_details': [{'id': item.id, 'score': round(score, 6), 'applicability_status': applicability[item.id]} for score, item in candidates],
            'applied_filters': applied_filters,
            'filter_counts': filter_counts,
            'missing_application_facts': missing_application_facts,
            'retrieval_query': text,
            'retrieval_run_id': str(uuid.uuid4()),
        }


class UserEvidenceRAGService:
    def search(self, query: EvidenceQuery) -> dict:
        query.validate()
        evidence = UserEvidence.objects.filter(organization_id=query.organization_id).select_related('chunk__resource', 'owner_user')
        filter_counts = {'organization_scope': evidence.count()}
        applied_filters = {'organization_id': query.organization_id, 'proposal_id': query.proposal_id}
        evidence = evidence.filter(Q(proposal__isnull=True) | Q(proposal_id=query.proposal_id))
        filter_counts['proposal_scope'] = evidence.count()
        if query.owner_id is None:
            evidence = evidence.exclude(authorization_scope='owner_private')
        else:
            evidence = evidence.filter(Q(owner_user_id__isnull=True) | Q(owner_user_id=query.owner_id))
            applied_filters['owner_id'] = query.owner_id
        evidence = evidence.exclude(authorization_scope='proposal', proposal__isnull=True)
        filter_counts['authorization_scope'] = evidence.count()
        if query.evidence_types:
            evidence = evidence.filter(chunk__chunk_type__in=query.evidence_types)
            applied_filters['evidence_types'] = list(query.evidence_types)
        filter_counts['after_evidence_type'] = evidence.count()
        if query.time_range:
            allowed_ids = []
            for item in evidence:
                facts = EvidenceFact.objects.filter(user_evidence=item).exclude(verification_status__in=['conflicted', 'rejected'])
                if facts.exists() and any(_time_matches(fact, query.time_range) for fact in facts):
                    allowed_ids.append(item.id)
            evidence = evidence.filter(id__in=allowed_ids)
            applied_filters['time_range'] = query.time_range
        filter_counts['after_time_range'] = evidence.count()
        text = ' '.join(rewrite_evidence_query(query)).strip()
        terms = _terms(text)
        vector = embed_texts([query_embedding_input(knowledge_domain='user_evidence', text=text)])[0] if text else []
        rows = []
        for item in evidence:
            denied = EvidenceAuthorization.objects.filter(
                user_evidence=item, allowed=False,
            ).filter(Q(proposal__isnull=True) | Q(proposal_id=query.proposal_id)).filter(
                Q(owner_user__isnull=True) | Q(owner_user_id=query.owner_id)
            ).exists()
            fact_statuses = list(EvidenceFact.objects.filter(user_evidence=item).values_list('verification_status', flat=True))
            if not denied and not (fact_statuses and all(status in {'rejected', 'conflicted'} for status in fact_statuses)):
                rows.append(item)
        dense = sorted(((_cosine(vector, item.chunk.embedding or []) if vector and item.chunk.embedding else 0.0, item) for item in rows), key=lambda item: (-item[0], item[1].id))[:40]
        lexical = sorted(((_overlap_score(terms, item.chunk.text), item) for item in rows), key=lambda item: (-item[0], item[1].id))[:30]
        candidates = _rrf(dense, lexical, 30)
        results = []
        ranked = []
        authorized_rows = {item.chunk_id: item for item in rows}
        for score, item in candidates:
            facts = list(EvidenceFact.objects.filter(user_evidence=item).exclude(verification_status__in=['conflicted', 'rejected']))
            fact_text = ' '.join(f'{fact.subject} {fact.predicate} {fact.object} {fact.numeric_value or ""}' for fact in facts)
            lexical_score = _overlap_score(terms, f'{item.chunk.text} {fact_text}')
            verified_score = sum(fact.verification_status == 'user_confirmed' for fact in facts)
            type_score = int(bool(query.evidence_types and item.chunk.chunk_type in query.evidence_types))
            intent_score = _overlap_score(_terms(query.claim_intent), fact_text) if query.claim_intent else 0
            ranked.append((score + lexical_score * 0.002 + verified_score * 0.01 + type_score * 0.01 + intent_score * 0.002, score, lexical_score, verified_score, type_score, intent_score, item, facts))
        ranked.sort(key=lambda item: (-item[0], item[-2].id))
        for final_score, base_score, lexical_score, verified_score, type_score, intent_score, item, facts in ranked[:8]:
            status = 'sufficient' if any(fact.verification_status == 'user_confirmed' for fact in facts) else 'partial'
            adjacent = [
                candidate for candidate in authorized_rows.values()
                if candidate.resource_id == item.resource_id and abs(candidate.chunk.chunk_index - item.chunk.chunk_index) == 1
            ]
            results.append({
                'user_evidence_id': item.id, 'chunk_id': item.chunk_id,
                'document_name': item.resource.display_name,
                'page_number': item.chunk.page_start,
                'text': item.chunk.text,
                'evidence_type': item.chunk.chunk_type,
                'facts': [{'fact_id': fact.id, 'status': fact.fact_status, 'project_status': fact.project_status, 'role': fact.user_role, 'author_order': fact.author_order, 'verification_status': fact.verification_status, 'numeric_value': str(fact.numeric_value or ''), 'unit': fact.unit, 'metric_definition': fact.metric_definition, 'authority_level': fact.authority_level} for fact in facts],
                'adjacent_evidence': [{'user_evidence_id': row.id, 'chunk_id': row.chunk_id, 'relationship': 'adjacent_same_authorized_resource'} for row in adjacent],
                'evidence_status': status, 'retrieval_score': round(final_score, 6),
                'ranking_factors': {'rrf': round(base_score, 6), 'lexical_overlap': lexical_score, 'verified_fact_count': verified_score, 'type_match': type_score, 'claim_intent_match': intent_score},
            })
        return {
            'status': 'ok' if results else 'missing_evidence',
            'results': results,
            'audit_candidates': [item.id for _, item in candidates],
            'audit_candidate_details': [{'id': item.id, 'score': round(score, 6)} for score, item in candidates],
            'applied_filters': applied_filters,
            'filter_counts': filter_counts,
            'retrieval_query': text,
            'retrieval_run_id': str(uuid.uuid4()),
        }
