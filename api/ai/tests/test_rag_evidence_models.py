import io

from django.db.models.deletion import ProtectedError
from django.test import TestCase
from reportlab.pdfgen import canvas

from ai.ingestion import IngestionError, create_resource_with_chunks, ingest_pdf
from ai.models import AIChunk, AIJob, EvidenceUsage


def make_pdf(text: str) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 720, text)
    document.showPage()
    document.save()
    return output.getvalue()


class RagEvidenceModelTests(TestCase):
    def test_chunk_id_is_stable_and_org_dedupe_is_isolated(self):
        kwargs = dict(type_='guideline', title='Guide', source_url='', full_text='Eligibility requirements apply.')
        first = create_resource_with_chunks(organization_id='org-a', **kwargs)
        second = create_resource_with_chunks(organization_id='org-a', **kwargs)
        other_org = create_resource_with_chunks(organization_id='org-b', **kwargs)
        self.assertEqual(first.id, second.id)
        self.assertNotEqual(first.id, other_org.id)
        self.assertEqual(first.chunks.first().stable_chunk_id, second.chunks.first().stable_chunk_id)

    def test_evidence_usage_protects_chunk_and_soft_deletes_resource(self):
        resource = create_resource_with_chunks(type_='guideline', title='Guide', source_url='', full_text='A factual constraint.', organization_id='org-a')
        chunk = resource.chunks.get()
        job = AIJob.objects.create(type='write')
        EvidenceUsage.objects.create(ai_job=job, chunk=chunk, role='writer', snapshot_text=chunk.text)
        with self.assertRaises(ProtectedError):
            chunk.delete()
        resource.delete()
        resource.refresh_from_db()
        self.assertTrue(resource.is_deleted)

    def test_pdf_ingestion_keeps_page_and_reports_ocr_requirement(self):
        resource = ingest_pdf(content=make_pdf('PDF evidence text'), filename='guide.pdf', organization_id='org-a')
        chunk = resource.chunks.get()
        self.assertEqual(chunk.page_start, 1)
        with self.assertRaisesRegex(IngestionError, 'ocr_required'):
            ingest_pdf(content=make_pdf(''), filename='scan.pdf', organization_id='org-a')
