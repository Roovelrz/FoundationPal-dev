import json
from pathlib import Path

from django.core.management.base import BaseCommand


def _blank(prefix, count, fields):
    return [{**{'case_id': f'{prefix}:{index:03d}', 'annotation_status': 'pending_human_review'}, **fields} for index in range(1, count + 1)]


class Command(BaseCommand):
    help = 'Export complete Phase 11 human annotation worklists from the frozen evaluation set.'

    def add_arguments(self, parser):
        parser.add_argument('--dataset', default='../data/phase11_frozen_eval_v1.json')
        parser.add_argument('--output-dir', default='../data/phase11_human_worklists')

    def handle(self, *args, **options):
        dataset = Path(options['dataset'])
        if not dataset.is_absolute():
            dataset = Path.cwd() / dataset
        rows = json.loads(dataset.read_text(encoding='utf-8'))['cases']
        confirmed = [item for item in rows if item.get('annotation_status') == 'human_confirmed']
        output = Path(options['output_dir'])
        if not output.is_absolute():
            output = Path.cwd() / output
        output.mkdir(parents=True, exist_ok=True)

        rule_rows = [item for item in confirmed if item.get('domain') == 'grant_rule' and item.get('answer_state') == 'answerable']
        evidence_rows = [item for item in confirmed if item.get('domain') == 'user_evidence' and item.get('answer_state') == 'answerable']
        rule = [{
            'case_id': item['case_id'], 'query': item['query'], 'gold_chunk_ids': item.get('gold_chunk_ids', []),
            'grant_pack_version_id': None, 'applicable_year': None, 'program_type': '', 'region': '',
            'requirement_ids': item.get('requirement_ids', []), 'annotation_notes': item.get('annotation_notes', ''),
        } for item in rule_rows]
        evidence = [{
            'case_id': item['case_id'], 'query': item['query'], 'gold_chunk_ids': item.get('gold_chunk_ids', []),
            'organization_id': '', 'proposal_id': None, 'user_evidence_ids': item.get('user_evidence_ids', []),
            'expected_role': '', 'expected_numeric_value': None, 'expected_fact_status': '', 'annotation_notes': item.get('annotation_notes', ''),
        } for item in evidence_rows]
        evidence.extend(_blank('new_user_evidence', 40 - len(evidence), {
            'query': '', 'gold_chunk_ids': [], 'organization_id': '', 'proposal_id': None, 'user_evidence_ids': [],
            'expected_role': '', 'expected_numeric_value': None, 'expected_fact_status': '', 'annotation_notes': '',
        }))
        negatives = _blank('no_applicable_rule_year', 12, {'query': '', 'grant_pack_version_id': None, 'requested_year': None, 'expected_status': 'no_applicable_rule', 'reason': 'wrong_year'})
        negatives += _blank('no_applicable_rule_program', 12, {'query': '', 'grant_pack_version_id': None, 'requested_program_type': '', 'expected_status': 'no_applicable_rule', 'reason': 'wrong_program'})
        negatives += _blank('no_applicable_rule_region', 12, {'query': '', 'grant_pack_version_id': None, 'requested_region': '', 'expected_status': 'no_applicable_rule', 'reason': 'wrong_region'})
        mixed = _blank('mixed', 24, {'query': '', 'grant_pack_version_id': None, 'requirement_ids': [], 'organization_id': '', 'user_evidence_ids': [], 'gold_chunk_ids': [], 'expected_answer': '', 'annotation_notes': ''})
        leakage = _blank('cross_org', 24, {'query': '', 'authorized_organization_id': '', 'distractor_organization_id': '', 'authorized_user_evidence_ids': [], 'forbidden_user_evidence_ids': [], 'expected_status': 'ok', 'annotation_notes': ''})
        claims = _blank('claim_grounding', 30, {'proposal_id': None, 'section_key': '', 'claim_text': '', 'claim_type': '', 'requirement_ids': [], 'user_evidence_ids': [], 'expected_status': '', 'expected_review_issue_codes': [], 'annotation_notes': ''})
        workflows = _blank('intake', 36, {'task_mode': '', 'quality_level': '', 'rule_readiness': '', 'content_maturity': '', 'evidence_readiness': '', 'expected_grill_mode': '', 'expected_max_questions': None, 'expected_blocking_topics': [], 'notes': ''})
        workflows += _blank('review_grill', 12, {'proposal_id': None, 'section_key': '', 'review_issue_code': '', 'expected_question': '', 'expected_affected_claim_ids': [], 'expected_resolution': '', 'notes': ''})
        files = {
            '01_rule_requirement_mapping.json': {'target_count': 154, 'cases': rule},
            '02_user_evidence_grounding.json': {'target_count': 40, 'cases': evidence},
            '03_negative_rule_scope.json': {'target_count': 36, 'cases': negatives},
            '04_mixed_dual_domain.json': {'target_count': 24, 'cases': mixed},
            '05_cross_organization_leakage.json': {'target_count': 24, 'cases': leakage},
            '06_claim_grounding.json': {'target_count': 30, 'cases': claims},
            '07_intake_and_review_workflow.json': {'target_count': 48, 'cases': workflows},
        }
        for name, value in files.items():
            (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        guides = {
            '01_rule_requirement_mapping.md': '逐条填写 grant_pack_version_id、applicable_year、program_type、region、requirement_ids。每条 requirement_ids 必须是当前数据库 GrantRequirement ID，并与 gold_chunk_ids 来源一致。',
            '02_user_evidence_grounding.md': '逐条填写 organization_id、proposal_id、user_evidence_ids、expected_role、expected_numeric_value、expected_fact_status。不得使用跨组织或未授权资料。',
            '03_negative_rule_scope.md': '每条填写真实规则包版本和故意不适用的年份、类别或地区。预期状态固定为 no_applicable_rule。',
            '04_mixed_dual_domain.md': '每条同时填写 requirement_ids、organization_id、user_evidence_ids 与 gold_chunk_ids，答案必须同时依赖规则和用户事实。',
            '05_cross_organization_leakage.md': '每条必须填写真实授权组织和真实干扰组织，且两侧存在相似资料。forbidden_user_evidence_ids 不能出现在授权组织检索结果中。',
            '06_claim_grounding.md': '每条填写 Claim 原文、对应 Requirement、UserEvidence、预期 Claim 状态与 ReviewIssue 代码。至少覆盖 supported、missing_evidence、conflicted 和 locked。',
            '07_intake_and_review_workflow.md': 'Intake 条目覆盖任务目标、交付深度、准备度、预期 Grill 路由和阻断项。Review Grill 条目填写 Issue、受影响 Claim 和预期人工决策。',
        }
        for name, text in guides.items():
            (output / name).write_text(f'# {name[:-3]}\n\n{text}\n', encoding='utf-8')
        manifest = {'schema_version': 'phase11_human_worklists_v1', 'frozen_confirmed_count': len(confirmed), 'worklists': [{'file': name, 'target_count': value['target_count'], 'actual_count': len(value['cases'])} for name, value in files.items()]}
        (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'phase11_human_worklists_exported: {output}'))
