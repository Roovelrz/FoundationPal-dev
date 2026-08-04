from django.test import TestCase
from django.contrib.auth import get_user_model
from orgs.models import Organization, OrgUser
from proposals.models import Proposal


class ProposalsOrgScopeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username='alice', password='p')
        self.bob = User.objects.create_user(username='bob', password='p')
        self.org = Organization.objects.create(name='Acme', admin=self.alice)
        OrgUser.objects.create(org=self.org, user=self.alice, role='admin')

    def test_list_requires_membership(self):
        self.client.force_login(self.bob)
        Proposal.objects.create(author=self.alice, org=self.org, content={'meta': {'title': 'T'}})
        r = self.client.get('/api/proposals/', HTTP_X_ORG_ID=str(self.org.id))  # type: ignore[arg-type]
        self.assertEqual(r.status_code, 200)
        data = r.json()
        items = data if isinstance(data, list) else data.get('results') or []
        self.assertEqual(len(items), 0)

    def test_create_rejects_an_explicit_workspace_without_membership(self):
        self.client.force_login(self.bob)
        r = self.client.post(
            '/api/proposals/',
            data={'content': {'meta': {'title': 'X'}}},
            content_type='application/json',
            HTTP_X_ORG_ID=str(self.org.id),  # type: ignore[arg-type]
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Proposal.objects.filter(author=self.bob).exists())

    def test_create_uses_the_explicit_workspace(self):
        self.client.force_login(self.alice)
        r = self.client.post(
            '/api/proposals/',
            data={'content': {'meta': {'title': 'Workspace project'}}},
            content_type='application/json',
            HTTP_X_ORG_ID=str(self.org.id),  # type: ignore[arg-type]
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['org'], self.org.id)
        self.assertEqual(Proposal.objects.get(id=r.json()['id']).org_id, self.org.id)

    def test_create_requires_an_explicit_workspace(self):
        self.client.force_login(self.bob)
        response = self.client.post(
            '/api/proposals/',
            data={'content': {'meta': {'title': 'One'}}},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['workspace'], 'workspace_required')

    def test_workspace_numbers_are_independent(self):
        second_org = Organization.objects.create(name='Beta', admin=self.alice)
        OrgUser.objects.create(org=second_org, user=self.alice, role='admin')
        self.client.force_login(self.alice)

        first = self.client.post(
            '/api/proposals/',
            data={'content': {'meta': {'title': 'A1'}}},
            content_type='application/json',
            HTTP_X_ORG_ID=str(self.org.id),
        )
        second = self.client.post(
            '/api/proposals/',
            data={'content': {'meta': {'title': 'B1'}}},
            content_type='application/json',
            HTTP_X_ORG_ID=str(second_org.id),
        )
        third = self.client.post(
            '/api/proposals/',
            data={'content': {'meta': {'title': 'A2'}}},
            content_type='application/json',
            HTTP_X_ORG_ID=str(self.org.id),
        )

        self.assertEqual([first.status_code, second.status_code, third.status_code], [201, 201, 201])
        self.assertEqual([first.json()['workspace_number'], second.json()['workspace_number'], third.json()['workspace_number']], [1, 1, 2])
