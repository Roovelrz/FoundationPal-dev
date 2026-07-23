from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from ai.models import AIMetric, WorkflowRun
from ai.validators import reviewer_or_human_review
from ai.workflow import resolve_run_id
from exports.models import ExportJob
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


class EvalBaselineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='eval-user', password='p')
        self.org = Organization.objects.create(name='eval-org', admin=self.user)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_happy_path_run_is_queryable(self):
        proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        response = self.api.post('/api/ai/plan', {'proposal_id': proposal.id, 'text_spec': 'Anonymous case'}, format='json')
        self.assertEqual(response.status_code, 200)
        run_id = response.json()['run_id']
        self.assertTrue(WorkflowRun.objects.filter(run_id=run_id).exists())
        self.assertTrue(AIMetric.objects.filter(run_id=run_id, type='plan', success=True).exists())

    def test_invalid_planner_case_preserves_database(self):
        proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        from unittest.mock import patch

        with patch('ai.views.get_provider') as factory:
            factory.return_value.plan.return_value = {'schema_version': 'v1', 'sections': []}
            response = self.api.post('/api/ai/plan', {'proposal_id': proposal.id, 'text_spec': 'Invalid'}, format='json')
        self.assertEqual(response.status_code, 502)
        self.assertFalse(ProposalSection.objects.filter(proposal=proposal).exists())

    def test_writer_failure_preserves_existing_draft(self):
        proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        section = ProposalSection.objects.create(proposal=proposal, key='summary', draft_content='existing')
        from unittest.mock import patch

        with patch('ai.views.get_provider') as factory:
            factory.return_value.write.side_effect = RuntimeError('provider failure')
            response = self.api.post('/api/ai/write', {'proposal_id': proposal.id, 'section_id': section.key, 'answers': {}}, format='json')
        self.assertEqual(response.status_code, 502)
        section.refresh_from_db()
        self.assertEqual(section.draft_content, 'existing')

    def test_reviewer_rewrite_case_does_not_promote(self):
        result = reviewer_or_human_review({'schema_version': 'v1', 'section_key': 'summary', 'decision': 'invalid'})
        self.assertEqual(result['decision'], 'human_review')

    def test_export_failure_case_creates_no_export(self):
        proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        run_id = resolve_run_id(None, proposal_id=proposal.id)
        response = self.api.post('/api/exports', {'proposal_id': proposal.id, 'format': 'docx', 'run_id': str(run_id)}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ExportJob.objects.filter(proposal=proposal).exists())
