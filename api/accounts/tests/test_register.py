from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from orgs.models import Organization, OrgUser


class RegisterTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def test_register_creates_user_personal_org_and_tokens(self):
        response = self.api.post(
            '/api/register',
            {'username': 'new-user', 'password': 'strong-pass'},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        user = get_user_model().objects.get(username='new-user')
        org = Organization.objects.get(admin=user)
        self.assertTrue(OrgUser.objects.filter(org=org, user=user, role='admin').exists())
        self.assertTrue(response.json()['access'])
        self.assertEqual(response.json()['org']['id'], org.id)

    def test_register_rejects_duplicate_username(self):
        get_user_model().objects.create_user(username='existing', password='strong-pass')

        response = self.api.post(
            '/api/register',
            {'username': 'existing', 'password': 'strong-pass'},
            format='json',
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['error'], 'username_taken')

    def test_register_rejects_short_password(self):
        response = self.api.post(
            '/api/register',
            {'username': 'short-password', 'password': 'short'},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()['error'], 'password_too_short')
