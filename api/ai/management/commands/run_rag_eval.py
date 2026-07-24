import json
import os
from pathlib import Path
from time import perf_counter

from django.core.management.base import BaseCommand, CommandError

from ai.embedding_service import EmbeddingService
from ai.retrieval import retrieve_top_k


class Command(BaseCommand):
    help = 'Run retrieval candidates for human RAG evaluation annotation.'

    def add_arguments(self, parser):
        parser.add_argument('--questions', required=True)
        parser.add_argument('--output-dir', default='reports')
        parser.add_argument('--organization-id', default='')
        parser.add_argument('--model-path', required=True)
        parser.add_argument('--top-k', type=int, default=5)

    def handle(self, *args, **options):
        path = Path(options['questions'])
        if not path.is_file():
            raise CommandError(f'questions_not_found: {path}')
        questions = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(questions, list) or not questions:
            raise CommandError('questions_empty')
        os.environ['EMBEDDING_BACKEND'] = 'bge'
        os.environ['BGE_MODEL_PATH'] = options['model_path']
        EmbeddingService.reset()
        service = EmbeddingService.instance()
        if service.backend != 'bge':
            raise CommandError('real_embedding_backend_required')
        results = []
        for question in questions:
            started = perf_counter()
            candidates = retrieve_top_k(
                question['query'],
                k=options['top_k'],
                organization_id=options['organization_id'],
                source_types=set(question.get('allowed_source_types', [])) or None,
            )
            results.append({
                'id': question['id'],
                'query': question['query'],
                'has_answer': question['has_answer'],
                'gold_chunk_ids': question.get('gold_chunk_ids', []),
                'elapsed_ms': round((perf_counter() - started) * 1000, 2),
                'candidates': candidates,
            })
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = {'model': service.health(), 'question_count': len(results), 'results': results}
        (output_dir / 'rag-initial-candidates.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['# RAG Initial Candidates', '', f'Model: {service.model_name}', '']
        for result in results:
            lines.extend([f'## {result["id"]}', '', f'Question: {result["query"]}', f'Has answer: {result["has_answer"]}', f'Gold chunk ids: {result["gold_chunk_ids"] or "PENDING"}', ''])
            for candidate in result['candidates']:
                lines.append(f'- Chunk {candidate["chunk_id"]} | score {candidate["score"]} | {candidate["document_name"]} | page {candidate["page_start"]}-{candidate["page_end"]}')
        (output_dir / 'rag-initial-candidates.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'首次评测完成：{len(results)} 个问题。'))
