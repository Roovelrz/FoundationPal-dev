from django.core.management.base import BaseCommand

from ai.domain_indexing import reindex_domain_resource
from ai.models import AIResource


class Command(BaseCommand):
    help = 'Reindex every classified dual-RAG resource without changing resource or chunk IDs.'

    def handle(self, *args, **options):
        resources = AIResource.objects.filter(knowledge_domain__in=['grant_rule', 'user_evidence'], is_deleted=False, status='ready').order_by('id')
        resource_count = 0
        chunk_count = 0
        for resource in resources:
            chunk_count += reindex_domain_resource(resource=resource)
            resource_count += 1
        self.stdout.write(self.style.SUCCESS(f'reindexed resources={resource_count} chunks={chunk_count}'))
