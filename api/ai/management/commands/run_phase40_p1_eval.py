import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ai.phase11_formal_eval import markdown, run_formal_eval
from ai.phase40_p1 import validate_holdout


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--base-input-dir', required=True)
        parser.add_argument('--output-dir', required=True)
        parser.add_argument('--mapping-kind-prefix', default='phase40_p0v5_')

    def handle(self, *args, **options):
        validation = validate_holdout(options['input_dir'], options['mapping_kind_prefix'])
        if not validation['valid']:
            raise CommandError('phase40_p1_holdout_invalid')
        root = Path(options['input_dir'])
        base = Path(options['base_input_dir'])
        merged = Path(options['output_dir']) / 'fixtures'
        merged.mkdir(parents=True, exist_ok=True)
        overrides = {'02_user_evidence_grounding.json', '04_mixed_dual_domain.json', '05_cross_organization_leakage.json'}
        required = ['01_rule_requirement_mapping.json', '02_user_evidence_grounding.json', '03_negative_rule_scope.json', '04_mixed_dual_domain.json', '05_cross_organization_leakage.json', '06_claim_grounding.json', '07_intake_and_review_workflow.json', '06_claim_citation_entailment_labels.json']
        for name in required:
            source = root / name if name in overrides else base / name
            if source.exists():
                (merged / name).write_bytes(source.read_bytes())
        report = run_formal_eval(merged, None, options['mapping_kind_prefix'])
        report['p1_holdout_validation'] = validation
        output = Path(options['output_dir'])
        (output / 'phase40-p1-formal-eval.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (output / 'phase40-p1-formal-eval.md').write_text(markdown(report), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('phase40_p1_eval_complete'))
