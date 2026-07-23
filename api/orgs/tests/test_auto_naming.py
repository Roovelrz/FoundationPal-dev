from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from billing.models import Subscription
from orgs.models import Organization


class OrganizationAutoNamingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='workspace-owner', password='p')
        self.api = APIClient()
        self.api.force_authenticate(user=self.user)

    def test_blank_names_are_numbered_in_creation_order(self):
        first = self.api.post('/api/orgs/', {'name': ''}, format='json')
        second = self.api.post('/api/orgs/', {}, format='json')

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(first.json()['name'], '工作区 1')
        self.assertEqual(second.json()['name'], '工作区 2')
        self.assertEqual(
            list(Organization.objects.filter(admin=self.user).values_list('name', flat=True)),
            ['工作区 1', '工作区 2'],
        )

    def test_pro_user_can_create_multiple_workspaces(self):
        Subscription.objects.create(owner_user=self.user, tier='pro', status='active')

        first = self.api.post('/api/orgs/', {}, format='json')
        second = self.api.post('/api/orgs/', {}, format='json')

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
