from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from ai.models import AIJob
from ai.tasks import run_write
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


@override_settings(AI_PROVIDER='stub', AI_ASYNC=False)
class WritePersistenceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='writer', password='p')
        self.org = Organization.objects.create(name='writer-org', admin=self.user)
        self.proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        self.section = ProposalSection.objects.create(
            proposal=self.proposal,
            key='intro',
            title='Introduction',
        )
        self.client.force_login(self.user)

    def test_sync_write_persists_draft_by_proposal_and_section_key(self):
        response = self.client.post(
            '/api/ai/write',
            data={
                'proposal_id': self.proposal.id,
                'section_id': self.section.key,
                'answers': {'objective': 'Build a verified workflow'},
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.section.refresh_from_db()
        self.assertEqual(self.section.draft_content, response.json()['draft_text'])
        self.assertEqual(self.section.content, '')
        self.assertEqual(self.section.approved_content, '')
        self.assertEqual(
            self.section.metadata['answers'],
            {'objective': 'Build a verified workflow'},
        )

    def test_async_write_persists_draft_by_proposal_and_section_key(self):
        job = AIJob.objects.create(
            type='write',
            input_json={
                'proposal_id': self.proposal.id,
                'section_id': self.section.key,
                'answers': {'objective': 'Persist an async draft'},
                'file_refs': [],
            },
            created_by=self.user,
            org_id=str(self.org.id),
        )

        run_write(job.id)

        job.refresh_from_db()
        self.section.refresh_from_db()
        self.assertEqual(job.status, 'done')
        self.assertEqual(self.section.draft_content, job.result_json['draft_text'])
        self.assertEqual(self.section.content, '')
        self.assertEqual(self.section.approved_content, '')
        self.assertEqual(
            self.section.metadata['answers'],
            {'objective': 'Persist an async draft'},
        )

    def test_sync_write_rejects_inaccessible_proposal(self):
        user_model = get_user_model()
        other_user = user_model.objects.create_user(username='other-writer', password='p')
        other_org = Organization.objects.create(name='other-writer-org', admin=other_user)
        other_proposal = Proposal.objects.create(author=other_user, org=other_org, content={})
        other_section = ProposalSection.objects.create(proposal=other_proposal, key='intro')

        response = self.client.post(
            '/api/ai/write',
            data={
                'proposal_id': other_proposal.id,
                'section_id': other_section.key,
                'answers': {'objective': 'Must not be saved'},
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)
        other_section.refresh_from_db()
        self.assertEqual(other_section.draft_content, '')
