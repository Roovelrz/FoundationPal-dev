import json
import random
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ai.providers.deepseek import DeepSeekProvider


class Command(BaseCommand):
    help = 'Judge a deterministic sample of RAG regression results with DeepSeek.'

    def add_arguments(self, parser):
        parser.add_argument('--regression', required=True)
        parser.add_argument('--cases', required=True)
        parser.add_argument('--output-dir', default='reports')
        parser.add_argument('--sample-size', type=int, default=30)
        parser.add_argument('--seed', type=int, default=20260724)
        parser.add_argument('--max-attempts', type=int, default=3)
        parser.add_argument('--batch-size', type=int, default=10)

    def handle(self, *args, **options):
        regression_path = Path(options['regression'])
        cases_path = Path(options['cases'])
        if not regression_path.is_absolute():
            regression_path = Path.cwd() / regression_path
        if not cases_path.is_absolute():
            cases_path = Path.cwd().parent / cases_path
        if not regression_path.is_file() or not cases_path.is_file():
            raise CommandError('judge_input_not_found')
        regression = json.loads(regression_path.read_text(encoding='utf-8'))
        loaded_cases = json.loads(cases_path.read_text(encoding='utf-8'))
        cases = loaded_cases.get('cases', loaded_cases)
        case_by_id = {item.get('case_id', item.get('id')): item for item in cases}
        results = list(regression.get('results') or [])
        if options['sample_size'] < 1 or len(results) < options['sample_size']:
            raise CommandError('judge_sample_size_invalid')
        random.Random(options['seed']).shuffle(results)
        output_dir = Path(options['output_dir'])
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        cache_path = output_dir / 'rag-judge-sample.json'
        cached = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {'results': []}
        judged = list(cached.get('results') or [])
        judged_ids = {item.get('case_id') for item in judged}
        provider = DeepSeekProvider()
        new_count = 0

        def save_cache():
            complete_count = sum(item['verdict']['coverage'] == 'complete' for item in judged)
            payload = {'target_sample_size': options['sample_size'], 'sample_size': len(judged), 'complete': len(judged) >= options['sample_size'], 'complete_answer_rate': round(complete_count / len(judged), 4) if judged else 0, 'results': judged}
            cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            (output_dir / 'rag-judge-sample.md').write_text(f'# RAG Judge Sample\n\n- Sample size: {len(judged)}\n- Complete answer rate: {payload["complete_answer_rate"]}\n', encoding='utf-8')
        for result in results:
            if len(judged) >= options['sample_size'] or new_count >= options['batch_size']:
                break
            if result.get('case_id') in judged_ids:
                continue
            case = case_by_id.get(result.get('case_id'))
            if not case:
                raise CommandError(f'judge_case_missing: {result.get("case_id")}')
            verdict = None
            for _ in range(options['max_attempts']):
                raw = provider.judge_rag_context(
                    query=case['query'],
                    reference_answer=case['reference_answer'],
                    candidates=result['candidates'][:5],
                )
                try:
                    candidate_verdict = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if candidate_verdict.get('coverage') in {'complete', 'partial', 'none'}:
                    verdict = candidate_verdict
                    break
            if verdict is None:
                self.stderr.write(f'judge_skipped: {result.get("case_id")}')
                continue
            judged.append({'case_id': result.get('case_id'), 'verdict': verdict})
            judged_ids.add(result.get('case_id'))
            new_count += 1
            save_cache()
        save_cache()
        self.stdout.write(self.style.SUCCESS(f'rag_judge_cached: {new_count} new, {len(judged)} total'))
