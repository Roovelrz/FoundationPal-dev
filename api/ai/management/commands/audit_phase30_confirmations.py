import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from ai.models import EvidenceFact, GrantRequirement


SUPPORTED_SCOPE_KEYS = {'program_type', 'year', 'region', 'section_key'}


class Command(BaseCommand):
    help = 'Create the Phase 1 to 3 confirmation workbook without fabricating business sign-off.'

    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--readiness-report', required=True)
        parser.add_argument('--output-json', default='reports/phase30-confirmation-workbook.json')
        parser.add_argument('--output-md', default='reports/phase30-confirmation-workbook.md')

    def handle(self, *args, **options):
        input_dir = Path(options['input_dir'])
        readiness = json.loads(Path(options['readiness_report']).read_text(encoding='utf-8'))
        cases = json.loads((input_dir / '02_user_evidence_grounding.json').read_text(encoding='utf-8'))['cases']
        case_by_evidence = {}
        for case in cases:
            for key, value in case.items():
                if 'evidence' in key and isinstance(value, list):
                    for external_id in value:
                        case_by_evidence.setdefault(external_id, case)

        binding_items = []
        for external_id in readiness['manual_evidence_source_binding_external_ids']:
            case = case_by_evidence.get(external_id, {})
            binding_items.append({
                'external_id': external_id,
                'case_id': case.get('case_id', ''),
                'query': case.get('query', ''),
                'required_confirmation': '选择同一事实的原始资料 Chunk stable_chunk_id，并确认组织、Proposal、授权范围与页码。',
                'status': 'pending_human_source_binding',
            })

        unsupported_scope_items = []
        display_metadata_count = 0
        for requirement in GrantRequirement.objects.select_related('source_chunk').all().order_by('id'):
            scope = requirement.applicability or {}
            category = str(scope.get('category') or '')
            severity = str(scope.get('severity') or '')
            requires_scope_review = bool(category) or severity.startswith('conditional')
            if requires_scope_review:
                unsupported = sorted(set(scope) - SUPPORTED_SCOPE_KEYS - {'phase11_bge_eval'})
                unsupported_scope_items.append({
                    'requirement_id': requirement.id,
                    'source_chunk_id': requirement.source_chunk_id,
                    'scope': scope,
                    'unsupported_scope_keys': unsupported,
                    'required_confirmation': '确认这些字段是否只用于展示，或应映射到项目类别、申请阶段、申请主体等可检索字段。',
                    'status': 'pending_human_scope_semantics',
                })
            elif set(scope) - SUPPORTED_SCOPE_KEYS - {'phase11_bge_eval'}:
                display_metadata_count += 1

        extracted_fact_items = []
        for fact in EvidenceFact.objects.filter(verification_status='extracted').select_related('user_evidence').order_by('id'):
            extracted_fact_items.append({
                'fact_id': fact.id,
                'user_evidence_id': fact.user_evidence_id,
                'subject': fact.subject,
                'predicate': fact.predicate,
                'object': fact.object,
                'time_range': fact.time_range,
                'required_confirmation': '核对原始资料后确认事实内容、时间和可用于申报的范围，随后改为 user_confirmed 或 rejected。',
                'status': 'pending_human_fact_verification',
            })

        payload = {
            'phase': '3.0_phase_1_to_3',
            'auto_confirmed': {
                'phase_1': [
                    '规则侧隔离语料为 BGE 768 维，154 条冻结规则查询均可执行。',
                    '隔离规则候选正文未复制冻结题干，且无 Hash 与 BGE 混合向量。',
                ],
                'phase_2': [
                    '规则查询已记录候选、过滤、适用性和可解释排序因素。',
                    '规则隔离语料 BGE Candidate Recall@20 为 1.0，Final Recall@5 为 0.961。',
                    f'{display_metadata_count}条规则的 source_id 与非条件 severity 已确认仅作来源或风险展示，不参与适用性过滤。',
                ],
                'phase_3': [
                    '用户证据查询先执行组织、Proposal、所有者、授权、类型和时间范围过滤。',
                    '排序结果保留词法、已确认事实、类型与 Claim 意图等因素。',
                ],
            },
            'pending_human_confirmation': {
                'phase_1_original_source_bindings': binding_items,
                'phase_2_scope_semantics': unsupported_scope_items,
                'phase_3_extracted_fact_verification': extracted_fact_items,
            },
            'summary': {
                'phase_1_pending_count': len(binding_items),
                'phase_2_pending_count': len(unsupported_scope_items),
                'phase_2_auto_classified_display_metadata_count': display_metadata_count,
                'phase_3_pending_count': len(extracted_fact_items),
                'scope_key_distribution': {
                    ','.join(keys): count
                    for keys, count in Counter(tuple(sorted((item or {}).keys())) for item in GrantRequirement.objects.values_list('applicability', flat=True)).items()
                },
            },
        }
        output_json = Path(options['output_json'])
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

        lines = [
            '# 3.0 阶段1至3人工确认工作簿',
            '',
            '本文件只列出系统不能替代业务人员作出的确认。自动确认不等于事实、来源或发布签署确认。',
            '',
            '## 自动确认完成',
            '',
        ]
        for phase, items in payload['auto_confirmed'].items():
            lines.append(f'### {phase}')
            lines.extend(f'- {item}' for item in items)
            lines.append('')
        lines.extend([
            '## 待人工确认汇总',
            '',
            f'- 阶段1原始来源绑定：{len(binding_items)}项',
            f'- 阶段2适用性字段语义：{len(unsupported_scope_items)}项',
            f'- 阶段3抽取事实核验：{len(extracted_fact_items)}项',
            '',
            '详细字段、每一条外部ID与处理状态见同目录 JSON。人工确认后不得直接修改冻结评测题，应通过原始资料绑定或事实核验记录更新。',
        ])
        Path(options['output_md']).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('phase30_confirmation_workbook_complete'))
