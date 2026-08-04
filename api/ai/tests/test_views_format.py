from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


@override_settings(AI_PROVIDER='gemini', AI_ASYNC=False)
class AIFormatEndpointTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='ai', password='p', email='ai@example.com')
        self.org = Organization.objects.create(name='AI Org', admin=self.user)
        self.proposal = Proposal.objects.create(
            author=self.user,
            org=self.org,
            content={'meta': {'full_draft_review': {'status': 'approved', 'version': 1}}},
        )
        ProposalSection.objects.create(
            proposal=self.proposal,
            key='section-a',
            title='Section A',
            state='approved',
            approved_content='Content here.',
            content='Content here.',
            locked=True,
        )
        self.api.force_authenticate(user=self.user)

    def test_format_endpoint_returns_formatted_text(self):
        payload = {
            'proposal_id': self.proposal.id,
            'template_hint': 'standard',
        }
        r = self.api.post('/api/ai/format', payload, format='json', HTTP_X_ORG_ID=str(self.org.id))
        assert r.status_code == 200, r.content
        data = r.json()
        assert 'formatted_text' in data
        assert data['formatted_text'].startswith('[gemini:final_format')
