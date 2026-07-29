from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ai.models import AIChunk, AIResource, UserEvidence
from orgs.models import Organization


class Command(BaseCommand):
    help = 'Classify one AIResource into a dual-RAG knowledge domain.'

    def add_arguments(self, parser):
        parser.add_argument('resource_id', type=int)
        parser.add_argument('knowledge_domain', choices=['grant_rule', 'user_evidence'])
        parser.add_argument('--organization-id', type=int)
        parser.add_argument('--actor', default='operator')

    def handle(self, *args, **options):
        resource = AIResource.objects.filter(pk=options['resource_id']).first()
        if resource is None:
            raise CommandError('resource_not_found')

        domain = options['knowledge_domain']
        organization_id = options.get('organization_id')
        if domain == 'user_evidence':
            if organization_id is None or not Organization.objects.filter(pk=organization_id).exists():
                raise CommandError('user_evidence_requires_existing_organization')

        metadata = dict(resource.metadata or {})
        audit = list(metadata.get('classification_audit', []))
        audit.append({
            'at': timezone.now().isoformat(),
            'actor': options['actor'],
            'knowledge_domain': domain,
            'organization_id': str(organization_id or ''),
        })
        metadata['classification_audit'] = audit
        classification_status = 'pack_draft' if domain == 'grant_rule' else 'classified'

        with transaction.atomic():
            AIResource.objects.filter(pk=resource.pk).update(
                organization_id=str(organization_id or resource.organization_id),
                knowledge_domain=domain,
                classification_status=classification_status,
                authorization_scope='organization',
                metadata=metadata,
            )
            AIChunk.objects.filter(resource_id=resource.pk).update(
                knowledge_domain=domain,
                index_namespace=domain,
            )
            if domain == 'user_evidence':
                for chunk_id in AIChunk.objects.filter(resource_id=resource.pk).values_list('id', flat=True):
                    UserEvidence.objects.get_or_create(
                        resource_id=resource.pk,
                        chunk_id=chunk_id,
                        defaults={
                            'organization_id': str(organization_id),
                            'authorization_scope': 'organization',
                        },
                    )

        self.stdout.write(self.style.SUCCESS(f'classified resource={resource.pk} domain={domain}'))
