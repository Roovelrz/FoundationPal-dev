import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from reportlab.pdfgen import canvas

from ai.models import AIResource


def pdf_bytes(text: str) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 720, text)
    document.save()
    return output.getvalue()


class ImportRagDocumentsCommandTests(TestCase):
    def write_manifest(self, directory: Path, rows: list[dict]) -> Path:
        manifest = directory / 'manifest.csv'
        with manifest.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=['filename', 'display_name', 'source_type', 'evidence_purpose', 'proposal_scope', 'notes'])
            writer.writeheader()
            writer.writerows(rows)
        return manifest

    def valid_row(self, filename='guide.pdf'):
        return {'filename': filename, 'display_name': 'Guide', 'source_type': 'guideline', 'evidence_purpose': 'constraint', 'proposal_scope': 'shared', 'notes': 'official'}

    def test_preview_has_no_writes_and_import_is_idempotent(self):
        with TemporaryDirectory() as value:
            directory = Path(value)
            (directory / 'guide.pdf').write_bytes(pdf_bytes('Guideline text'))
            manifest = self.write_manifest(directory, [self.valid_row()])
            call_command('import_rag_documents', manifest=str(manifest), pdf_dir=str(directory), dry_run=True)
            self.assertEqual(AIResource.objects.count(), 0)
            call_command('import_rag_documents', manifest=str(manifest), pdf_dir=str(directory), organization_id='org-a')
            call_command('import_rag_documents', manifest=str(manifest), pdf_dir=str(directory), organization_id='org-a')
            resource = AIResource.objects.get()
            self.assertEqual(AIResource.objects.count(), 1)
            self.assertEqual(resource.source_type, 'guideline')
            self.assertEqual(resource.evidence_purpose, 'constraint')
            self.assertEqual(resource.metadata['proposal_scope'], 'shared')

    def test_invalid_enum_missing_file_and_manifest_duplicate_fail(self):
        with TemporaryDirectory() as value:
            directory = Path(value)
            (directory / 'guide.pdf').write_bytes(pdf_bytes('Guideline text'))
            invalid = self.valid_row()
            invalid['source_type'] = 'invalid'
            with self.assertRaisesRegex(CommandError, 'invalid_source_type'):
                call_command('import_rag_documents', manifest=str(self.write_manifest(directory, [invalid])), pdf_dir=str(directory))
            missing = self.valid_row('missing.pdf')
            with self.assertRaisesRegex(CommandError, 'pdf_not_found'):
                call_command('import_rag_documents', manifest=str(self.write_manifest(directory, [missing])), pdf_dir=str(directory))
            with self.assertRaisesRegex(CommandError, 'duplicate_conflict'):
                call_command('import_rag_documents', manifest=str(self.write_manifest(directory, [self.valid_row(), self.valid_row()])), pdf_dir=str(directory))
