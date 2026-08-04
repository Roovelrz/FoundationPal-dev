from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from ai.models import AIJob
from ai.tasks import run_revise
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


@override_settings(AI_PROVIDER='stub', AI_ASYNC=False)
class RevisePersistenceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='reviewer', password='p')
        self.org = Organization.objects.create(name='reviewer-org', admin=self.user)
        self.proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        self.section = ProposalSection.objects.create(
            proposal=self.proposal,
            key='intro',
            title='Introduction',
            draft_content='Original draft',
        )
        self.client.force_login(self.user)

    def test_sync_revise_updates_draft_and_appends_revision(self):
        response = self.client.post(
            '/api/ai/revise',
            data={
                'proposal_id': self.proposal.id,
                'section_id': self.section.key,
                'base_text': self.section.draft_content,
                'change_request': 'Add evidence',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.section.refresh_from_db()
        self.assertEqual(self.section.draft_content, response.json()['draft_text'])
        self.assertEqual(self.section.content, '')
        self.assertEqual(self.section.approved_content, '')
        self.assertEqual(len(self.section.revisions), 1)
        self.assertEqual(self.section.revisions[0]['from'], 'Original draft')
        self.assertEqual(self.section.revisions[0]['to'], response.json()['draft_text'])
        self.assertIsInstance(response.json()['diff'], dict)

    def test_direct_draft_save_keeps_only_the_immediate_previous_version(self):
        first = self.client.patch(
            f'/api/ai/sections/{self.section.id}/draft',
            data={'draft_text': 'User edited draft'},
            content_type='application/json',
        )

        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()['previous_draft'], 'Original draft')
        self.section.refresh_from_db()
        self.assertEqual(self.section.draft_content, 'User edited draft')
        self.assertEqual(self.section.revisions[-1]['from'], 'Original draft')

        detail = self.client.get(f'/api/proposals/{self.proposal.id}/')
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()['sections'][0]['previous_draft'], 'Original draft')

    def test_async_revise_updates_same_section_by_proposal_and_key(self):
        job = AIJob.objects.create(
            type='revise',
            input_json={
                'proposal_id': self.proposal.id,
                'section_id': self.section.key,
                'base_text': self.section.draft_content,
                'change_request': 'Clarify the method',
                'file_refs': [],
            },
            created_by=self.user,
            org_id=str(self.org.id),
        )

        run_revise(job.id)

        job.refresh_from_db()
        self.section.refresh_from_db()
        self.assertEqual(job.status, 'done')
        self.assertEqual(self.section.draft_content, job.result_json['draft_text'])
        self.assertEqual(self.section.content, '')
        self.assertEqual(self.section.approved_content, '')
        self.assertEqual(len(self.section.revisions), 1)

    def test_sync_revise_rejects_inaccessible_proposal(self):
        user_model = get_user_model()
        other_user = user_model.objects.create_user(username='other-reviewer', password='p')
        other_org = Organization.objects.create(name='other-reviewer-org', admin=other_user)
        other_proposal = Proposal.objects.create(author=other_user, org=other_org, content={})
        other_section = ProposalSection.objects.create(
            proposal=other_proposal,
            key='intro',
            draft_content='Protected draft',
        )

        response = self.client.post(
            '/api/ai/revise',
            data={
                'proposal_id': other_proposal.id,
                'section_id': other_section.key,
                'base_text': other_section.draft_content,
                'change_request': 'Must not be saved',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)
        other_section.refresh_from_db()
        self.assertEqual(other_section.draft_content, 'Protected draft')

    @override_settings(PROPOSAL_SECTION_REVISION_CAP=1)
    def test_sync_revise_ignores_legacy_cap_for_section_key(self):
        self.section.revisions = [{'from': 'A', 'to': 'B'}]
        self.section.save(update_fields=['revisions', 'updated_at'])

        response = self.client.post(
            '/api/ai/revise',
            data={
                'proposal_id': self.proposal.id,
                'section_id': self.section.key,
                'base_text': self.section.draft_content,
                'change_request': '仍可继续修订',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.section.refresh_from_db()
        self.assertNotEqual(self.section.draft_content, 'Original draft')
        self.assertEqual(len(self.section.revisions), 2)
