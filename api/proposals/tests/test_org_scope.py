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

    def test_personal_org_reused_across_multiple_creations(self):
        self.client.force_login(self.bob)
        first = self.client.post(
            '/api/proposals/',
            data={'content': {'meta': {'title': 'One'}}},
            content_type='application/json',
        )
        self.assertIn(first.status_code, (200, 201))
        first_org_id = first.json().get('org')
        self.assertIsNotNone(first_org_id)
        before_org_ids = set(OrgUser.objects.filter(user=self.bob).values_list('org_id', flat=True))
        second = self.client.post(
            '/api/proposals/',
            data={'content': {'meta': {'title': 'Two'}}},
            content_type='application/json',
        )
        self.assertIn(second.status_code, (200, 201, 402))
        after_org_ids = set(OrgUser.objects.filter(user=self.bob).values_list('org_id', flat=True))
        self.assertEqual(before_org_ids, after_org_ids)
        if second.status_code in (200, 201):
            self.assertEqual(second.json().get('org'), first_org_id)
