from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from proposals.models import Proposal
from orgs.models import Organization, OrgUser


class EditAndArchiveTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.u = self.User.objects.create_user(username='u1', password='x', email='u1@example.com')
        self.org = Organization.objects.create(name='工作区 1', admin=self.u)
        OrgUser.objects.create(org=self.org, user=self.u, role='admin')
        self.client = APIClient()
        # Issue token via SimpleJWT directly by logging in through /api/token in DEBUG may be AllowAny; use force_authenticate equivalent
        self.client.force_authenticate(self.u)

    def test_edit_allowed_at_cap(self):
        # Free tier with active cap 1
        p = Proposal.objects.create(author=self.u, org=self.org, content={'meta': {'title': 'One'}, 'sections': {}}, schema_version='v1')
        # Create second should be blocked (middleware/permission would handle in live path). We focus on PATCH allowed.
        res = self.client.patch(
            f'/api/proposals/{p.id}/', data={'content': {'meta': {'title': 'Updated'}, 'sections': {}}}, format='json'
        )
        self.assertEqual(res.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.content.get('meta', {}).get('title'), 'Updated')

    def test_free_can_archive(self):
        p = Proposal.objects.create(author=self.u, org=self.org, content={'meta': {'title': 'One'}}, schema_version='v1')
        res = self.client.patch(f'/api/proposals/{p.id}/', data={'state': 'archived'}, format='json')
        self.assertEqual(res.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.state, 'archived')

    def test_unarchive_is_available_without_a_quota(self):
        p = Proposal.objects.create(author=self.u, org=self.org, content={'meta': {'title': 'One'}}, schema_version='v1', state='archived')
        Proposal.objects.create(author=self.u, org=self.org, content={'meta': {'title': 'Two'}}, schema_version='v1')
        res = self.client.patch(f'/api/proposals/{p.id}/', data={'state': 'draft'}, format='json')
        self.assertEqual(res.status_code, 200)

    def test_delete_soft_archives_for_an_ordinary_user(self):
        p = Proposal.objects.create(author=self.u, org=self.org, content={'meta': {'title': 'One'}}, schema_version='v1')
        res = self.client.delete(f'/api/proposals/{p.id}/')
        self.assertIn(res.status_code, (204, 200))
        res = self.client.delete(f'/api/proposals/{p.id}/')
        self.assertIn(res.status_code, (204, 200))
        p.refresh_from_db()
        self.assertEqual(p.state, 'archived')
