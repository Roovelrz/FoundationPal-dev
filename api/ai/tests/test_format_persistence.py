from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from ai.models import AIJob
from ai.tasks import run_format
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


@override_settings(AI_PROVIDER='gemini', AI_ASYNC=False)
class FormatPersistenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='formatter', password='p')
        self.org = Organization.objects.create(name='Format Org', admin=self.user)
        self.proposal = Proposal.objects.create(
            author=self.user,
            org=self.org,
            content={'meta': {'title': 'Fund Proposal'}},
        )
        ProposalSection.objects.create(
            proposal=self.proposal,
            key='summary',
            title='Summary',
            order=1,
            state='approved',
            approved_content='Approved summary',
            content='Approved summary',
            draft_content='Approved summary',
            locked=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(user=self.user)

    def test_sync_format_persists_final_markdown_from_approved_sections(self):
        response = self.api.post(
            '/api/ai/format',
            {
                'proposal_id': self.proposal.id,
                'full_text': 'Untrusted client copy',
                'template_hint': 'standard',
            },
            format='json',
            HTTP_X_ORG_ID=str(self.org.id),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.final_markdown, response.json()['formatted_text'])
        self.assertIn('Approved summary', self.proposal.final_markdown)
        self.assertNotIn('Untrusted client copy', self.proposal.final_markdown)

    def test_async_format_persists_final_markdown(self):
        job = AIJob.objects.create(
            type='format',
            input_json={
                'proposal_id': self.proposal.id,
                'full_text': '# Fund Proposal\n\n## Summary\nApproved summary',
            },
            created_by=self.user,
            org_id=self.org.id,
        )

        run_format(job.id)

        job.refresh_from_db()
        self.proposal.refresh_from_db()
        self.assertEqual(job.status, 'done')
        self.assertEqual(self.proposal.final_markdown, job.result_json['formatted_text'])

    def test_format_rejects_unapproved_sections(self):
        ProposalSection.objects.create(
            proposal=self.proposal,
            key='plan',
            title='Plan',
            order=2,
            state='draft',
            draft_content='Unapproved plan',
        )

        response = self.api.post(
            '/api/ai/format',
            {'proposal_id': self.proposal.id},
            format='json',
            HTTP_X_ORG_ID=str(self.org.id),
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['error'], 'sections_not_approved')

