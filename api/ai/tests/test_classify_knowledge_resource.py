from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ai.ingestion import create_resource_with_chunks
from ai.models import UserEvidence
from orgs.models import Organization
from django.contrib.auth import get_user_model


class ClassifyKnowledgeResourceCommandTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='owner', password='pass')
        self.organization = Organization.objects.create(name='Org', admin=user)
        self.resource = create_resource_with_chunks(
            type_='team_profile',
            title='Team profile',
            source_url='',
            full_text='Team evidence.',
        )

    def test_user_evidence_classification_requires_existing_organization(self):
        with self.assertRaises(CommandError):
            call_command('classify_knowledge_resource', self.resource.id, 'user_evidence')

        call_command(
            'classify_knowledge_resource',
            self.resource.id,
            'user_evidence',
            organization_id=self.organization.id,
            actor='test',
            stdout=StringIO(),
        )
        self.resource.refresh_from_db()
        chunk = self.resource.chunks.get()
        self.assertEqual(self.resource.organization_id, str(self.organization.id))
        self.assertEqual(self.resource.knowledge_domain, 'user_evidence')
        self.assertEqual(chunk.index_namespace, 'user_evidence')
        self.assertEqual(UserEvidence.objects.filter(resource=self.resource, chunk=chunk).count(), 1)
        self.assertEqual(self.resource.metadata['classification_audit'][-1]['actor'], 'test')
