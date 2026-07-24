from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from ai.models import AIMetric
from orgs.models import Organization, OrgUser
from proposals.models import Proposal, ProposalSection


class AIMetricsProposalSectionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='u2', email='u2@example.com', password='pw')
        self.client.force_authenticate(self.user)
        self.org = Organization.objects.create(name='Metric Org', admin=self.user)
        OrgUser.objects.create(org=self.org, user=self.user, role='admin')

    def test_write_records_proposal_and_section(self):
        proposal = Proposal.objects.create(author=self.user, org=self.org)
        ProposalSection.objects.create(proposal=proposal, key='s1')
        payload = {
            'proposal_id': proposal.id,
            'section_id': 's1',
            'answers': {'q': 'a'},
            'file_refs': [],
        }
        resp = self.client.post('/api/ai/write', payload, format='json', HTTP_X_ORG_ID=str(self.org.id))
        self.assertEqual(resp.status_code, 200)
        m = AIMetric.objects.filter(type='write').order_by('-id').first()
        self.assertIsNotNone(m)
        self.assertEqual(m.proposal_id, payload['proposal_id'])
        self.assertEqual(m.section_id, 's1')

    def test_revise_records_proposal_and_section(self):
        proposal = Proposal.objects.create(author=self.user, org=self.org)
        ProposalSection.objects.create(proposal=proposal, key='s2')
        payload = {
            'proposal_id': proposal.id,
            'section_id': 's2',
            'base_text': 'hello',
            'change_request': 'shorter',
            'file_refs': [],
        }
        resp = self.client.post('/api/ai/revise', payload, format='json', HTTP_X_ORG_ID=str(self.org.id))
        self.assertEqual(resp.status_code, 200)
        m = AIMetric.objects.filter(type='revise').order_by('-id').first()
        self.assertIsNotNone(m)
        self.assertEqual(m.proposal_id, payload['proposal_id'])
        self.assertEqual(m.section_id, 's2')
