from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


@override_settings(AI_PROVIDER='stub')
class AIUnlimitedAccessTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.user = get_user_model().objects.create_user(username='ordinary-user', password='p')
        self.org = Organization.objects.create(name='Ordinary user org', admin=self.user)
        self.proposal = Proposal.objects.create(
            author=self.user,
            org=self.org,
            content={'meta': {'full_draft_review': {'status': 'approved', 'version': 1}}},
        )
        ProposalSection.objects.create(
            proposal=self.proposal,
            key='summary',
            state='approved',
            approved_content='Approved content',
            content='Approved content',
            locked=True,
        )
        self.api.force_authenticate(user=self.user)

    @override_settings(DEBUG=False, AI_TEST_OPEN=False)
    def test_authenticated_user_can_use_all_authoring_actions_without_subscription(self):
        write = self.api.post('/api/ai/write', {'section_id': 'summary', 'answers': {'目标': '影响'}}, format='json')
        revise = self.api.post('/api/ai/revise', {'base_text': '基础内容', 'change_request': '扩展说明'}, format='json')
        final = self.api.post('/api/ai/format', {'proposal_id': self.proposal.id, 'template_hint': 'standard'}, format='json')

        self.assertEqual(write.status_code, 200, write.content)
        self.assertEqual(revise.status_code, 200, revise.content)
        self.assertEqual(final.status_code, 200, final.content)

    @override_settings(DEBUG=False, AI_TEST_OPEN=False)
    def test_unauthenticated_user_is_still_rejected(self):
        anonymous = APIClient()
        response = anonymous.post('/api/ai/write', {'section_id': 'summary', 'answers': {}}, format='json')
        self.assertEqual(response.status_code, 401)
