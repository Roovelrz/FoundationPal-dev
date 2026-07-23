from django.test import SimpleTestCase

from ai.validators import SchemaError, reviewer_or_human_review, validate_role_output


def planner_sample(**overrides):
    sample = {
        'schema_version': 'v1',
        'sections': [
            {
                'section_key': 'background',
                'title': 'Background',
                'questions': ['What problem will this proposal solve?'],
            }
        ],
    }
    sample.update(overrides)
    return sample


def writer_sample(**overrides):
    sample = {
        'schema_version': 'v1',
        'section_key': 'background',
        'draft_markdown': '## Background\nA valid draft.',
        'evidence_ids': [],
        'warnings': [],
        'missing_evidence': [],
    }
    sample.update(overrides)
    return sample


def review_sample(**overrides):
    sample = {
        'schema_version': 'v1',
        'section_key': 'background',
        'decision': 'rewrite',
        'issues': [],
        'required_changes': [],
        'protected_facts': [],
        'evidence_gaps': [],
    }
    sample.update(overrides)
    return sample


class StructuredOutputSchemaTests(SimpleTestCase):
    def test_planner_valid_and_invalid_samples(self):
        invalid_samples = [
            {},
            {'schema_version': 'v2', 'sections': []},
            {'schema_version': 'v1', 'sections': [{}]},
            planner_sample(sections=[]),
            planner_sample(sections=[{'section_key': 'x', 'title': 'X', 'questions': []}]),
            planner_sample(sections=[{'section_key': 'x', 'title': '', 'questions': ['Q']}]),
            planner_sample(sections=[{'section_key': '', 'title': 'X', 'questions': ['Q']}]),
            planner_sample(sections=[{'section_key': 'x', 'title': 'X', 'questions': ['']}]),
            planner_sample(sections=[{'section_key': 'x', 'title': 'X', 'questions': ['Q']}] * 13),
            planner_sample(sections=[{'section_key': 'x', 'title': 'X', 'questions': ['Q'] * 21}]),
        ]
        self.assertEqual(validate_role_output('plan', planner_sample()), planner_sample())
        for sample in invalid_samples:
            with self.subTest(sample=sample):
                with self.assertRaises(SchemaError):
                    validate_role_output('plan', sample)

    def test_writer_valid_and_invalid_samples(self):
        invalid_samples = [
            {},
            writer_sample(schema_version='v2'),
            writer_sample(section_key=''),
            writer_sample(draft_markdown=''),
            writer_sample(draft_markdown='{}'),
            writer_sample(draft_markdown='x' * 20001),
            writer_sample(evidence_ids='wrong'),
            writer_sample(warnings='wrong'),
            writer_sample(missing_evidence='wrong'),
            {'schema_version': 'v1', 'section_key': 'x', 'draft_markdown': 'text'},
        ]
        self.assertEqual(validate_role_output('write', writer_sample()), writer_sample())
        for sample in invalid_samples:
            with self.subTest(sample=sample):
                with self.assertRaises(SchemaError):
                    validate_role_output('write', sample)

    def test_reviewer_valid_and_invalid_samples(self):
        invalid_samples = [
            {},
            review_sample(schema_version='v2'),
            review_sample(section_key=''),
            review_sample(decision='reject'),
            review_sample(issues='wrong'),
            review_sample(required_changes='wrong'),
            review_sample(protected_facts='wrong'),
            review_sample(evidence_gaps='wrong'),
            {'schema_version': 'v1', 'section_key': 'x', 'decision': 'approve'},
            review_sample(decision=None),
        ]
        self.assertEqual(validate_role_output('review', review_sample()), review_sample())
        for sample in invalid_samples:
            with self.subTest(sample=sample):
                with self.assertRaises(SchemaError):
                    validate_role_output('review', sample)

    def test_invalid_reviewer_decision_routes_to_human_review(self):
        result = reviewer_or_human_review(review_sample(decision='reject'))
        self.assertEqual(result['decision'], 'human_review')
