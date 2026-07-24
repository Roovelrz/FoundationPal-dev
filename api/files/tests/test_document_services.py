from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from django.test import TestCase

from files.document_services import DocumentServiceError, extract_document_structure, extract_requirements, parse_pdf_bytes


class PdfCorpusTests(TestCase):
    corpus_dir = Path(__file__).resolve().parents[3] / 'data' / 'testpdf'

    def parse(self, filename):
        return parse_pdf_bytes((self.corpus_dir / filename).read_bytes(), filename=filename)

    def test_ten_pdf_corpus_has_expected_outcomes(self):
        accepted = {
            '01_small_text_valid.pdf': 1,
            '02_multi_page_valid.pdf': 12,
            '03_chinese_unicode_valid.pdf': 2,
            '04_table_and_form_valid.pdf': 2,
            '06_mixed_text_and_scan.pdf': 3,
        }
        for filename, page_count in accepted.items():
            with self.subTest(filename=filename):
                self.assertEqual(self.parse(filename)['page_count'], page_count)

        expected_errors = {
            '05_scanned_image_only.pdf': 'ocr_required',
            '07_encrypted_password_mcp-test.pdf': 'pdf_encrypted',
            '08_corrupt_truncated.pdf': 'pdf_parse_failed',
            '09_oversized_valid.pdf': 'file_too_large',
            '10_many_pages_300.pdf': 'page_limit_exceeded',
        }
        for filename, error_code in expected_errors.items():
            with self.subTest(filename=filename):
                with self.assertRaisesRegex(DocumentServiceError, error_code):
                    self.parse(filename)

    def test_structure_and_requirements_share_document_schema(self):
        document = self.parse('01_small_text_valid.pdf')
        structure = extract_document_structure(document)
        requirements = extract_requirements(document)
        self.assertEqual(structure['schema_version'], document['schema_version'])
        self.assertEqual(requirements['schema_version'], document['schema_version'])
        self.assertEqual(structure['page_count'], document['page_count'])

    def test_parallel_corpus_requests_are_bounded(self):
        filenames = [
            '01_small_text_valid.pdf',
            '02_multi_page_valid.pdf',
            '03_chinese_unicode_valid.pdf',
            '04_table_and_form_valid.pdf',
            '05_scanned_image_only.pdf',
            '06_mixed_text_and_scan.pdf',
        ]

        def parse(filename):
            try:
                return self.parse(filename).get('schema_version')
            except DocumentServiceError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=10) as executor:
            outcomes = list(executor.map(parse, filenames * 2))
        self.assertTrue(all(value in {'v1', 'ocr_required', 'parse_concurrency_limited'} for value in outcomes))
