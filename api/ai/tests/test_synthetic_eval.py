import json

from django.test import SimpleTestCase

from ai.synthetic_eval import SyntheticEvalRequest, build_case


class SyntheticEvalTests(SimpleTestCase):
    def setUp(self):
        self.request = SyntheticEvalRequest(
            chunk_id=7,
            resource_id=2,
            source_type='guideline',
            parser_version='pdfminer-v1',
            query_type='direct',
            evidence='申请人应当具有高级专业技术职务或者博士学位。',
        )

    def test_build_case_keeps_traceability_fields(self):
        raw = json.dumps({
            'usable': True,
            'query': '申请人需要具备什么资格？',
            'reference_answer': '应具有高级专业技术职务或者博士学位。',
            'query_type': 'direct',
        })
        case = build_case(self.request, raw, 'synthetic_0001', 'deepseek-chat')
        self.assertEqual(case['source_chunk_ids'], [7])
        self.assertEqual(case['source_document_ids'], [2])
        self.assertEqual(case['generation_prompt_version'], 'synthetic_eval_v1')

    def test_build_case_rejects_query_type_drift(self):
        raw = json.dumps({
            'usable': True,
            'query': '申请人需要具备什么资格？',
            'reference_answer': '应具有高级专业技术职务或者博士学位。',
            'query_type': 'negative',
        })
        with self.assertRaises(ValueError):
            build_case(self.request, raw, 'synthetic_0001', 'deepseek-chat')

    def test_build_case_skips_unusable_evidence(self):
        raw = json.dumps({'usable': False, 'query': '', 'reference_answer': '', 'query_type': 'direct'})
        self.assertIsNone(build_case(self.request, raw, 'synthetic_0001', 'deepseek-chat'))

    def test_build_case_rejects_empty_model_response(self):
        with self.assertRaises(ValueError):
            build_case(self.request, '', 'synthetic_0001', 'deepseek-chat')
