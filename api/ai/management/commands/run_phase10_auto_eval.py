import json
from pathlib import Path

from django.core.management.base import BaseCommand

from ai.observability import build_phase10_report, markdown_report
from ai.phase10_eval import run_automatic_phase10_evaluation


class Command(BaseCommand):
    help = 'Run anonymous automatic Phase 10 evaluation with DeepSeek judging.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default='reports')

    def handle(self, *args, **options):
        org_id, cases = run_automatic_phase10_evaluation()
        total = len(cases)
        automatic = {
            'context_recall_at_3': round(sum(item['context_recall_at_3'] for item in cases) / total, 4),
            'no_answer_correctness': round(sum(item['no_answer_correct'] for item in cases) / total, 4),
            'faithfulness': round(sum(item['faithful'] for item in cases) / total, 4),
            'case_count': total,
            'judge_token_usage': sum(item['judge_usage']['total_tokens'] for item in cases),
            'judge_estimated_cost_usd': round(sum(item['judge_estimated_cost_usd'] for item in cases), 8),
        }
        report = build_phase10_report(organization_id=org_id)
        report['automatic_eval'] = automatic
        report['rag'].update(automatic)
        report['rag']['not_measured'] = []
        out = Path(options['output_dir'])
        out.mkdir(parents=True, exist_ok=True)
        (out / 'phase10-auto-eval.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (out / 'phase10-auto-eval.md').write_text(markdown_report(report), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'phase10_auto_eval_complete: {total} cases'))
