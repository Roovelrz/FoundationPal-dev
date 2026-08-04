from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


@override_settings(AI_PROVIDER='stub', AI_ENFORCE_RATE_LIMIT_DEBUG=True, AI_RATE_PER_MIN_PRO=1, DEBUG=True)
class AIRateLimitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='ratelimit', password='test12345')
        self.client.force_login(self.user)

    def test_repeated_writes_are_not_rate_limited(self):
        data = {'section_id': 's1', 'answers': {'目标': '普通用户可重复生成'}}
        first = self.client.post('/api/ai/write', data=data, content_type='application/json')
        second = self.client.post('/api/ai/write', data=data, content_type='application/json')
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 200, second.content)
