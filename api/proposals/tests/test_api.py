from django.test import TestCase
from django.contrib.auth import get_user_model
from orgs.models import Organization, OrgUser


class ProposalsApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='apiuser', password='p')
        self.org = Organization.objects.create(name='工作区 1', admin=self.user)
        OrgUser.objects.create(org=self.org, user=self.user, role='admin')

    def test_list_endpoint_accessible_or_auth_required(self):
        resp = self.client.get('/api/proposals/')
        self.assertIn(resp.status_code, (200, 302, 401, 403))

    def test_create_multiple_proposals_without_a_quota(self):
        self.client.force_login(self.user)
        resp1 = self.client.post(
            '/api/proposals/',
            data={'content': {'title': 'Test'}},
            content_type='application/json',
            HTTP_X_ORG_ID=str(self.org.id),
        )
        self.assertEqual(resp1.status_code, 201)
        resp2 = self.client.post(
            '/api/proposals/',
            data={'content': {'title': 'Test 2'}},
            content_type='application/json',
            HTTP_X_ORG_ID=str(self.org.id),
        )
        self.assertEqual(resp2.status_code, 201)
        self.assertEqual(resp1.json()['workspace_number'], 1)
        self.assertEqual(resp2.json()['workspace_number'], 2)

    def test_call_url_write_once(self):
        self.client.force_login(self.user)
        # First proposal with call_url
        r1 = self.client.post(
            '/api/proposals/',
            data={'content': {'title': 'With URL'}, 'call_url': 'https://example.org/call'},
            content_type='application/json',
            HTTP_X_ORG_ID=str(self.org.id),
        )
        # Allow either 201 or 200 depending on renderer
        self.assertIn(r1.status_code, (200, 201))
        pid = r1.json()['id']
        # Attempt to change call_url
        r2 = self.client.patch(
            f'/api/proposals/{pid}/',
            data={'call_url': 'https://malicious.example/change'},
            content_type='application/json',
        )
        self.assertIn(r2.status_code, (200, 202))
        self.assertEqual(r2.json()['call_url'], 'https://example.org/call')
