from django.db.models import Count

from .domain_retrieval import EvidenceQuery, RuleQuery
from .models import Claim, GrillSession, GrantPackVersion, UserEvidence
from .query_router import search_grant_rules, search_user_evidence


def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def run_phase11_small_eval():
    rule_cases = []
    for version in GrantPackVersion.objects.filter(status='published').order_by('id')[:5]:
        result = search_grant_rules(RuleQuery(pack_version_id=version.id, year=version.year, user_question='requirements'))
        wrong_year = search_grant_rules(RuleQuery(pack_version_id=version.id, year=version.year + 1, user_question='requirements'))
        rule_cases.append({'pack_version_id': version.id, 'ok': result['status'] == 'ok', 'traceable': all(item.get('chunk_id') and item.get('source_document') for item in result['results']), 'wrong_year_rejected': wrong_year['status'] == 'no_applicable_rule'})
    evidence_cases = []
    for evidence in UserEvidence.objects.order_by('id')[:10]:
        result = search_user_evidence(EvidenceQuery(organization_id=evidence.organization_id, proposal_id=evidence.proposal_id, user_question='evidence'))
        own_ids = {item['user_evidence_id'] for item in result['results']}
        other = search_user_evidence(EvidenceQuery(organization_id='phase11-cross-org', user_question='evidence'))
        evidence_cases.append({'user_evidence_id': evidence.id, 'returned': evidence.id in own_ids, 'cross_org_missing': other['status'] == 'missing_evidence'})
    rule_total = len(rule_cases)
    evidence_total = len(evidence_cases)
    rule_report = {'report_type': 'rule_rag_small_eval', 'case_count': rule_total, 'recall_at_5': _ratio(sum(item['ok'] for item in rule_cases), rule_total), 'wrong_year_rejection_rate': _ratio(sum(item['wrong_year_rejected'] for item in rule_cases), rule_total), 'citation_traceability_rate': _ratio(sum(item['traceable'] for item in rule_cases), rule_total), 'cases': rule_cases}
    evidence_report = {'report_type': 'user_evidence_small_eval', 'case_count': evidence_total, 'context_recall_at_8': _ratio(sum(item['returned'] for item in evidence_cases), evidence_total), 'cross_organization_leakage_rate': 0.0 if all(item['cross_org_missing'] for item in evidence_cases) else 1.0, 'cases': evidence_cases}
    sessions = GrillSession.objects.all()
    intake_report = {'report_type': 'intake_grill_small_eval', 'session_count': sessions.count(), 'mode_counts': dict(sessions.values_list('mode').annotate(count=Count('id'))), 'average_questions': _ratio(sum(sessions.values_list('question_count', flat=True)), sessions.count()), 'completion_count': sessions.filter(status='completed').count()}
    claims = Claim.objects.all()
    e2e_report = {'report_type': 'claim_generation_small_eval', 'claim_count': claims.count(), 'claim_support_rate': _ratio(claims.exclude(status='missing_evidence').count(), claims.count()), 'unsupported_claim_rate': _ratio(claims.filter(claim_type='unsupported').count(), claims.count()), 'locked_claim_count': claims.filter(status='locked').count()}
    return {'evaluation_scope': 'small_eval_only', 'embedding_comparison': 'unchanged_embedding_only', 'rule_rag': rule_report, 'user_evidence_rag': evidence_report, 'intake_grill': intake_report, 'end_to_end': e2e_report}
