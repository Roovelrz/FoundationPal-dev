import json
import random
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ai.models import AIChunk
from ai.providers.deepseek import DeepSeekProvider
from ai.synthetic_eval import PROMPT_VERSION, SyntheticEvalRequest, build_case


QUERY_TYPES = ['direct'] * 40 + ['paraphrase'] * 30 + ['condition'] * 15 + ['negative'] * 10 + ['multi_info'] * 5


class Command(BaseCommand):
    help = 'Generate cached synthetic answerable RAG evaluation cases from existing chunks.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100)
        parser.add_argument('--output', default='data/rag_synthetic_eval_v1.json')
        parser.add_argument('--seed', type=int, default=20260724)
        parser.add_argument('--max-attempts', type=int, default=3)
        parser.add_argument('--workers', type=int, default=4)

    def handle(self, *args, **options):
        count = options['count']
        if count < 1:
            raise CommandError('count_must_be_positive')
        if options['max_attempts'] < 1 or options['workers'] < 1:
            raise CommandError('attempts_and_workers_must_be_positive')
        output_path = Path(options['output'])
        if not output_path.is_absolute():
            output_path = Path.cwd().parent / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._load_cache(output_path)
        cases = payload['cases']
        if len(cases) >= count:
            self.stdout.write(self.style.SUCCESS(f'synthetic_eval_cached: {len(cases)} cases'))
            return

        used_chunk_ids = {case['source_chunk_ids'][0] for case in cases}
        chunks = list(
            AIChunk.objects.filter(resource__status='ready', resource__is_deleted=False)
            .select_related('resource')
            .order_by('id')
        )
        eligible = [chunk for chunk in chunks if chunk.id not in used_chunk_ids and self._is_eligible(chunk.text)]
        random.Random(options['seed']).shuffle(eligible)
        required = count - len(cases)
        if len(eligible) < required:
            raise CommandError(f'eligible_chunks_insufficient: need={required} available={len(eligible)}')

        provider = DeepSeekProvider()
        generated = 0
        failed_chunks = []
        iterator = iter(eligible)
        while generated < required:
            batch = list(islice(iterator, options['workers']))
            if not batch:
                break
            requests = [
                SyntheticEvalRequest(
                    chunk_id=chunk.id,
                    resource_id=chunk.resource_id,
                    source_type=chunk.resource.source_type,
                    parser_version=chunk.resource.parser_version,
                    query_type=QUERY_TYPES[(len(cases) + generated + index) % len(QUERY_TYPES)],
                    evidence=chunk.text,
                )
                for index, chunk in enumerate(batch)
            ]
            with ThreadPoolExecutor(max_workers=options['workers']) as executor:
                futures = [executor.submit(self._generate_case, provider, request, options['max_attempts']) for request in requests]
                outcomes = [future.result() for future in futures]
            for request, case, error in outcomes:
                if generated >= required:
                    break
                if error:
                    failed_chunks.append(f'{request.chunk_id}:{error}')
                    self.stderr.write(f'synthetic_eval_skipped: chunk={request.chunk_id} error={error}')
                    continue
                if case is None:
                    continue
                case['case_id'] = f'synthetic_{len(cases) + 1:04d}'
                cases.append(case)
                generated += 1
                payload['cases'] = cases
                self._write_cache(output_path, payload)

        if generated != required:
            failures = ','.join(failed_chunks[:10]) or 'unusable_evidence'
            raise CommandError(f'synthetic_eval_incomplete: generated={generated} failures={failures}')
        self.stdout.write(self.style.SUCCESS(f'synthetic_eval_generated: {generated} new, {len(cases)} total'))

    @staticmethod
    def _is_eligible(text):
        compact = ''.join((text or '').split())
        return 100 <= len(compact) <= 1200

    @staticmethod
    def _generate_case(provider, request, max_attempts):
        error = ''
        for _ in range(max_attempts):
            try:
                raw = provider.generate_synthetic_eval_case(request)
                case = build_case(request, raw, 'pending', provider.model)
            except (json.JSONDecodeError, ValueError) as exc:
                error = str(exc)
                continue
            return request, case, ''
        return request, None, error

    @staticmethod
    def _load_cache(path):
        if not path.exists():
            return {'generation_prompt_version': PROMPT_VERSION, 'cases': []}
        payload = json.loads(path.read_text(encoding='utf-8'))
        if payload.get('generation_prompt_version') != PROMPT_VERSION or not isinstance(payload.get('cases'), list):
            raise CommandError('synthetic_eval_cache_invalid')
        return payload

    @staticmethod
    def _write_cache(path, payload):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
