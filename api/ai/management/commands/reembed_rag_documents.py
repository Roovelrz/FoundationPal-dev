import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ai.embedding_service import EmbeddingService
from ai.models import AIChunk, AIResource


class Command(BaseCommand):
    help = 'Rebuild RAG chunk embeddings with the local BGE model.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-id', default='')
        parser.add_argument('--model-path', required=True)
        parser.add_argument('--batch-size', type=int, default=16)

    def handle(self, *args, **options):
        os.environ['EMBEDDING_BACKEND'] = 'bge'
        os.environ['BGE_MODEL_PATH'] = options['model_path']
        EmbeddingService.reset()
        service = EmbeddingService.instance()
        if service.backend != 'bge':
            raise CommandError('real_embedding_backend_required')
        chunks = AIChunk.objects.filter(resource__organization_id=options['organization_id'], resource__is_deleted=False).select_related('resource').order_by('id')
        chunk_list = list(chunks)
        if not chunk_list:
            raise CommandError('no_rag_chunks_found')
        batch_size = max(1, options['batch_size'])
        with transaction.atomic():
            for start in range(0, len(chunk_list), batch_size):
                batch = chunk_list[start : start + batch_size]
                vectors = service.embed(chunk.text for chunk in batch)
                for chunk, vector in zip(batch, vectors):
                    chunk.embedding = vector
                    chunk.embedding_model = service.model_name
                    chunk.embedding_dimension = service.dim
                    chunk.save(update_fields=['embedding', 'embedding_model', 'embedding_dimension'])
            AIResource.objects.filter(id__in={chunk.resource_id for chunk in chunk_list}).update(
                embedding_model=service.model_name,
                embedding_revision=service.model_revision,
                embedding_dimension=service.dim,
            )
        self.stdout.write(self.style.SUCCESS(f'重嵌入完成：{len(chunk_list)} 个 Chunk，{service.model_name}，{service.dim} 维。'))
