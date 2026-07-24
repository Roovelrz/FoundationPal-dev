from django.test import TestCase
from ai.ingestion import create_resource_with_chunks
from ai.models import AIResource


class IngestionSimilarityDedupeTests(TestCase):
    def test_changed_document_creates_new_resource_version(self):
        base = 'This is a simple grant template text about health and education.'
        r1 = create_resource_with_chunks(type_='template', title='T1', source_url='', full_text=base)
        # Changed content is a new version and must not overwrite prior evidence.
        variant = base + ' Impact.'
        r2 = create_resource_with_chunks(type_='template', title='T2', source_url='', full_text=variant)
        self.assertNotEqual(r1.id, r2.id)
        self.assertEqual(AIResource.objects.filter(source_type='template').count(), 2)

    def test_different_below_threshold_creates_new(self):
        base = 'Funding science initiatives in rural areas with community outreach.'
        r1 = create_resource_with_chunks(type_='template', title='A', source_url='', full_text=base)
        # Make a sufficiently different text
        different = 'Completely unrelated agricultural policy document focusing on soil management.'  # noqa: E501
        r2 = create_resource_with_chunks(type_='template', title='B', source_url='', full_text=different)
        self.assertNotEqual(r1.id, r2.id)
        self.assertEqual(AIResource.objects.filter(source_type='template').count(), 2)
