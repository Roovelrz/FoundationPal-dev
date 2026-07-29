import json
from pathlib import Path

from django.core.management.base import BaseCommand


def load(root, name):
    return json.loads((root / name).read_text(encoding='utf-8'))['cases']


class Command(BaseCommand):
    help = 'Export all outstanding Phase 3.0 human data and approval worklists as paired Markdown and JSON files.'

    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--output-dir', required=True)

    def handle(self, *args, **options):
        root, output = Path(options['input_dir']), Path(options['output_dir'])
        output.mkdir(parents=True, exist_ok=True)
        bindings = json.loads((root / 'phase11_original_evidence_bindings.json').read_text(encoding='utf-8'))['cases']
        citations = json.loads((root / '06_claim_citation_entailment_labels.json').read_text(encoding='utf-8'))['cases']
        mixed = load(root, '04_mixed_dual_domain.json')
        workflow = load(root, '07_intake_and_review_workflow.json')
        risks = json.loads((root / 'phase30_reviewer_risk_matrix.json').read_text(encoding='utf-8'))['cases']
        groups = {
            '01_original_evidence': ('真实原始证据替换', bindings, '逐条替换当前开发构造来源。必须填写原始稳定 Chunk、页码、组织、Proposal、授权、审核人和日期。'),
            '02_citation_entailment': ('Citation 业务复核', citations, '逐条以原始证据页码复核 Claim 蕴含标签，并由业务审核人签署。'),
            '03_rule_applicability': ('规则适用性确认', [{'requirement_id': value, 'required_fact': fact, 'business_confirmation': ''} for value, fact in [(11, 'ethics_or_technology_safety'), (19, 'joint_application'), (20, 'out_of_province_affiliation'), (21, 'ethics_or_human_genetic_resource'), (24, 'program_category=youth_a'), (25, 'program_category=youth_a'), (26, 'program_category=youth_a'), (27, 'program_category=youth_b'), (28, 'program_category=youth_b'), (29, 'program_category=youth_b'), (30, 'program_category=youth_b'), (39, 'program_category=major and completion_review')]], '确认12条规则映射是否符合业务规则包原文，并记录审核依据页码。'),
            '04_dual_domain': ('双域子问题与 Gold 审核', mixed, '逐条确认规则子问题、事实子问题、两域 Gold 和联合答案边界。'),
            '05_reviewer_risk_cases': ('Reviewer 可执行风险样本', risks, '为608条矩阵记录补充 Claim、EvidenceFact、Decision Ledger、预期 Issue 与复核结果，使其可执行并用于计算分类指标。'),
            '06_intake_and_grill': ('Intake 与 Grill 合同审核', workflow, '为36条 Intake 和12条 Review Grill 夹具确认输入草稿、证据状态、预期路由、目标 Issue 与关闭条件。'),
            '07_release_signoff': ('发布签署', [{'area': value, 'owner': '', 'decision': '', 'date': '', 'evidence_report': ''} for value in ['真实来源替换', 'Citation 页码与蕴含', 'BGE 规则与用户证据', '组织隔离', 'Reviewer 指标', 'Review Grill 复核', 'Intake 指标', '发布保留集']], '在真实来源、独立发布保留集和全部指标复测完成后，由对应负责人签署。'),
        }
        index = []
        for stem, (title, cases, instruction) in groups.items():
            payload = {'group': title, 'required_count': len(cases), 'instruction': instruction, 'cases': cases}
            (output / f'{stem}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            md = f'# {title}\n\n数量：{len(cases)}\n\n{instruction}\n\n填写后保留每条记录的审核人、日期、原始来源或决定依据。\n'
            (output / f'{stem}.md').write_text(md, encoding='utf-8')
            index.append({'group': title, 'count': len(cases), 'md': f'{stem}.md', 'json': f'{stem}.json'})
        (output / '00_人工补充与审核总清单.json').write_text(json.dumps({'groups': index}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        lines = ['# Phase 3.0 人工补充与审核总清单', '', '以下每组均有同名 JSON 填写模板。先完成真实来源替换和 Citation 复核，再进行发布签署。', '', '| 组别 | 数量 | Markdown | JSON |', '| --- | ---: | --- | --- |']
        lines.extend(f"| {item['group']} | {item['count']} | {item['md']} | {item['json']} |" for item in index)
        (output / '00_人工补充与审核总清单.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'phase30_human_completion_pack_exported:{len(groups)}'))
