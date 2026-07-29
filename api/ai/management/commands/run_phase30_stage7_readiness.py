import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand


FREEZE_PER_RISK = {'positive': 10, 'near_negative': 10, 'boundary': 5}
DEVELOPMENT_PER_RISK = {'positive': 5, 'near_negative': 5, 'boundary': 3}


class Command(BaseCommand):
    help = 'Audit Phase 7 frozen-evaluation and release readiness without generating synthetic approvals.'

    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--reports-dir', required=True)
        parser.add_argument('--output-json', required=True)
        parser.add_argument('--output-md', required=True)

    def handle(self, *args, **options):
        root = Path(options['input_dir'])
        reports = Path(options['reports_dir'])
        workflow_cases = json.loads((root / '07_intake_and_review_workflow.json').read_text(encoding='utf-8'))['cases']
        review_cases = [item for item in workflow_cases if item['case_id'].startswith('review_grill:')]
        counts = Counter(item['review_issue_code'] for item in review_cases)
        readiness = json.loads((reports / 'phase11-bge-corpus-readiness.json').read_text(encoding='utf-8'))
        confirmation = json.loads((reports / 'phase30-confirmation-workbook.json').read_text(encoding='utf-8'))
        workflow = json.loads((reports / 'phase11-claim-workflow.json').read_text(encoding='utf-8'))
        formal = json.loads((reports / 'phase11-formal-eval.json').read_text(encoding='utf-8'))
        risks = []
        for code in sorted(counts):
            current = counts[code]
            risks.append({
                'code': code,
                'current_frozen_case_count': current,
                'freeze_required': FREEZE_PER_RISK,
                'freeze_missing': {key: max(value - current, 0) for key, value in FREEZE_PER_RISK.items()},
                'development_required': DEVELOPMENT_PER_RISK,
                'development_missing': {key: max(value - current, 0) for key, value in DEVELOPMENT_PER_RISK.items()},
            })
        reviewer = workflow['reviewer_execution']
        blockers = [
            {'id': 'phase1_source_binding', 'count': len(readiness['manual_evidence_source_binding_external_ids']), 'owner': 'evidence_reviewer', 'action': '绑定原始 Gold Chunk 并确认授权、组织、Proposal 和页码。'},
            {'id': 'phase2_scope_semantics', 'count': confirmation['summary']['phase_2_pending_count'], 'owner': 'rule_reviewer', 'action': '确认 conditional 与青年 A、B 类规则的适用字段映射。'},
            {'id': 'citation_entailment_labels', 'count': 'unquantified', 'owner': 'claim_reviewer', 'action': '为 Claim 与证据标注完整支持、部分支持或不支持。'},
            {'id': 'unimplemented_review_detectors', 'count': len(reviewer['expected_review_grill_issue_codes_not_implemented']), 'owner': 'reviewer_product_owner', 'action': '实现并人工确认剩余风险检测器。'},
            {'id': 'frozen_test_overfitting_risk', 'count': 1, 'owner': 'evaluation_owner', 'action': '建立未参与调参的开发集和独立发布保留集后，重新签署门槛。'},
        ]
        if formal['rule_rag']['unpublished_pack_safety_block_status'] != 'measured':
            blockers.append({'id': 'unpublished_pack_safety_fixture_gap', 'count': 1, 'owner': 'rule_reviewer', 'action': '补充并人工确认预期为 grant_pack_not_published 的冻结安全阻断样本。'})
        intake = workflow['intake_execution']
        if intake['routing_accuracy'] != 1 or intake['question_budget_accuracy'] != 1:
            blockers.append({
                'id': 'intake_fixture_contract_gap', 'count': 1, 'owner': 'intake_product_owner', 'action': '逐条复核36条 Intake 夹具与当前路由、问题预算合同的差异，并决定修正实现或更新人工标签。'})
        payload = {
            'phase': '3.0_phase_7',
            'release_ready': False,
            'risk_case_readiness': risks,
            'reviewer_detector_status': {
                'implemented_expected_codes': reviewer['expected_review_grill_issue_codes_implemented'],
                'not_implemented_codes': reviewer['expected_review_grill_issue_codes_not_implemented'],
                'not_observed_codes': reviewer['expected_review_grill_issue_codes_not_observed'],
            },
            'metric_status': {
                'rule_bge_status': readiness['semantic_baseline_status'],
                'user_evidence_bge_status': readiness['user_evidence_semantic_baseline_status'],
                'citation_entailment_status': formal['citation_metrics']['citation_entailment_status'],
                'cross_organization_leakage_rate': formal['user_evidence_rag']['cross_organization_leakage_rate'],
                'unpublished_pack_safety_block_rate': formal['rule_rag']['unpublished_pack_safety_block_rate'],
                'unpublished_pack_safety_block_status': formal['rule_rag']['unpublished_pack_safety_block_status'],
                'intake_routing_accuracy': intake['routing_accuracy'],
                'intake_question_budget_accuracy': intake['question_budget_accuracy'],
            },
            'blockers': blockers,
        }
        output_json = Path(options['output_json'])
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = [
            '# 0-7人工审核清单总表',
            '',
            '本表包含阶段0至7的全部人工审核任务，以及实施过程中确认未关闭的问题。系统当前不具备发布就绪条件。',
            '',
            '## 发布结论',
            '',
            '- 当前状态：不可发布。',
            '- 原因：用户证据 BGE 基线被18条来源绑定阻断，12条规则适用语义待确认，6类 Reviewer 风险未实现，冻结风险样本每类仅1条，未发布规则包安全阻断尚无期望样本。',
            '',
            '## 阶段0至4',
            '',
            '- 阶段0：人工标注 Claim 与证据的完整支持、部分支持或不支持，并签署评测夹具版本。',
            '- 阶段1：完成18条原始 Gold Chunk 来源绑定，确认授权、组织、Proposal 和页码。',
            '- 阶段2：完成12条 conditional 或青年 A、B 类规则的适用语义确认。',
            '- 阶段3：阶段1绑定完成后，审核用户证据 BGE 指标。',
            '- 阶段4：阶段1绑定完成后，审核24条双域样本的子问题、证据组合和 BGE Joint Recall。',
            '',
            '## 阶段5至6',
            '',
            '- 审核已实现检测器的业务真值和误报。',
            '- 为 duplicate_funding_conflict、locked_claim_change_attempt、role_attribution_conflict、metric_definition_conflict、cross_section_consistency、overclaiming 提供定义、样本和实现优先级。',
            '- 为12类风险分别签署允许处置、补充材料要求和关闭条件。',
            '',
            '## 阶段7冻结数据',
            '',
            '| 风险类型 | 当前冻结样本 | 开发集缺口 | 冻结集缺口 |',
            '| --- | ---: | --- | --- |',
        ]
        for item in risks:
            development = '、'.join(f'{key}{value}' for key, value in item['development_missing'].items())
            frozen = '、'.join(f'{key}{value}' for key, value in item['freeze_missing'].items())
            lines.append(f"| {item['code']} | {item['current_frozen_case_count']} | {development} | {frozen} |")
        lines.extend([
            '',
            '## 实施中发现且未关闭的问题',
            '',
        ])
        for blocker in blockers:
            lines.append(f"- {blocker['id']}：{blocker['action']}")
        lines.extend([
            '',
            '## 操作顺序',
            '',
            '1. 先完成阶段1和阶段2人工确认。',
            '2. 建立独立开发集和发布保留集，避免继续用冻结集调参。',
            '3. 补齐6类 Reviewer 检测器与12类风险样本。',
            '4. 逐条复核 Intake 夹具合同差异。',
            '5. 重跑 BGE、双域、Reviewer、Review Grill 和发布门槛报告，再由业务负责人签署。',
        ])
        Path(options['output_md']).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('phase30_stage7_readiness_complete'))
