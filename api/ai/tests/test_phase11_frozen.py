import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from ai.phase11_frozen import frozen_eval_report


class Phase11FrozenEvalTests(SimpleTestCase):
    def test_rejects_unconfirmed_and_accepts_complete_label_schema(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'cases.json'
            cases = [{'case_id': 'a', 'domain': 'grant_rule', 'query': 'q', 'answer_state': 'answerable', 'annotation_status': 'human_confirmed', 'requirement_ids': [1]}] * 165
            cases[0] = {'case_id': 'mixed', 'domain': 'mixed', 'query': 'q', 'answer_state': 'answerable', 'annotation_status': 'human_confirmed', 'requirement_ids': [1], 'user_evidence_ids': [1]}
            cases[1] = {'case_id': 'evidence', 'domain': 'user_evidence', 'query': 'q', 'answer_state': 'answerable', 'annotation_status': 'human_confirmed', 'user_evidence_ids': [1]}
            path.write_text(json.dumps({'cases': cases}), encoding='utf-8')
            report = frozen_eval_report(path)
            self.assertTrue(report['ready_for_formal_comparison'])

    def test_allows_three_documented_pending_cases_to_be_excluded(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'cases.json'
            rule = {'case_id': 'r', 'domain': 'grant_rule', 'query': 'q', 'answer_state': 'answerable', 'annotation_status': 'human_confirmed', 'gold_chunk_ids': [1]}
            evidence = {'case_id': 'e', 'domain': 'user_evidence', 'query': 'q', 'answer_state': 'missing_evidence', 'annotation_status': 'human_confirmed'}
            pending = {'case_id': 'p', 'domain': 'grant_rule', 'query': 'q', 'answer_state': 'answerable', 'annotation_status': 'pending_human_review', 'annotation_notes': 'source answer truncated'}
            path.write_text(json.dumps({'cases': [rule] * 159 + [evidence] * 3 + [pending] * 3}), encoding='utf-8')
            report = frozen_eval_report(path)
            self.assertTrue(report['ready_for_formal_comparison'])
            self.assertEqual(report['excluded_pending_review_count'], 3)
