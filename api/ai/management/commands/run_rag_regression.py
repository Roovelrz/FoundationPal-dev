import json
import os
from pathlib import Path
from time import perf_counter

from django.core.management.base import BaseCommand, CommandError

from ai.embedding_service import EmbeddingService
from ai.retrieval import RetrievalService


class Command(BaseCommand):
    help = 'Run dense RAG regression against manual or synthetic evaluation cases.'

    def add_arguments(self, parser):
        parser.add_argument('--cases', required=True)
        parser.add_argument('--output-dir', default='reports')
        parser.add_argument('--model-path', required=True)
        parser.add_argument('--organization-id', default='')

    def handle(self, *args, **options):
        cases_path = Path(options['cases'])
        if not cases_path.is_absolute():
            cases_path = Path.cwd().parent / cases_path
        if not cases_path.is_file():
            raise CommandError(f'cases_not_found: {cases_path}')
        loaded = json.loads(cases_path.read_text(encoding='utf-8'))
        cases = loaded.get('cases', loaded) if isinstance(loaded, dict) else loaded
        if not isinstance(cases, list) or not cases:
            raise CommandError('cases_empty')
        os.environ['EMBEDDING_BACKEND'] = 'bge'
        os.environ['BGE_MODEL_PATH'] = options['model_path']
        EmbeddingService.reset()
        service = EmbeddingService.instance()
        if service.backend != 'bge':
            raise CommandError('real_embedding_backend_required')
        retriever = RetrievalService()
        results = []
        hits = {1: 0, 3: 0, 5: 0, 20: 0}
        answerable = 0
        for case in cases:
            started = perf_counter()
            candidates = retriever.retrieve(
                case['query'],
                organization_id=options['organization_id'],
                source_types={case['source_type']} if case.get('source_type') else None,
                dense_top_k=20,
                final_top_k=20,
            )
            gold = set(case.get('source_chunk_ids') or case.get('gold_chunk_ids') or [])
            if case.get('answerable', case.get('has_answer', True)):
                answerable += 1
                candidate_ids = [candidate['chunk_id'] for candidate in candidates]
                for k in hits:
                    if gold.intersection(candidate_ids[:k]):
                        hits[k] += 1
            results.append({
                'case_id': case.get('case_id', case.get('id')),
                'query': case['query'],
                'gold_chunk_ids': sorted(gold),
                'elapsed_ms': round((perf_counter() - started) * 1000, 2),
                'candidates': candidates,
            })
        metrics = {f'id_recall_at_{k}': round(hits[k] / answerable, 4) if answerable else 0 for k in hits}
        metrics['average_elapsed_ms'] = round(sum(item['elapsed_ms'] for item in results) / len(results), 2)
        output_dir = Path(options['output_dir'])
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = {'model': service.health(), 'case_count': len(results), 'metrics': metrics, 'results': results}
        (output_dir / 'rag-regression.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['# RAG Regression Report', '', f'Cases: {len(results)}', '']
        lines.extend([f'- {name}: {value}' for name, value in metrics.items()])
        (output_dir / 'rag-regression.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'rag_regression_complete: {len(results)} cases'))
