from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from typing import Any, cast
import time
from django.contrib.auth import get_user_model
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


@override_settings(
    DEBUG=True,  # AllowAny on endpoints
    AI_ASYNC=1,
    CELERY_TASK_ALWAYS_EAGER=True,  # Run Celery tasks synchronously in-process
    CELERY_BROKER_URL='memory://',
    AI_PROVIDER='stub',
)
class AIAsyncJobTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='async', password='p')
        self.org = Organization.objects.create(name='Async Org', admin=self.user)
        self.proposal = Proposal.objects.create(
            author=self.user,
            org=self.org,
            content={'meta': {'full_draft_review': {'status': 'approved', 'version': 1}}},
        )
        ProposalSection.objects.create(
            proposal=self.proposal,
            key='summary',
            title='Summary',
            state='approved',
            approved_content='Hello world',
            content='Hello world',
            locked=True,
        )
        self.api.force_authenticate(user=self.user)

    def _wait_for_done(self, job_id: int, timeout_s: float = 2.0):
        t0 = time.time()
        last = None
        while time.time() - t0 < timeout_s:
            resp_any = cast(Any, self.api.get(f'/api/ai/jobs/{job_id}'))
            assert resp_any.status_code == 200
            last = resp_any.json()
            if last.get('status') in {'done', 'error'}:
                return last
            time.sleep(0.05)
        return last

    def test_async_write_job_succeeds(self):
        r_any = cast(
            Any,
            self.api.post(
                '/api/ai/write',
                {'section_id': 'summary', 'answers': {'objective': 'impact'}},
                format='json',
            ),
        )
        assert r_any.status_code == 200
        data = r_any.json()
        assert 'job_id' in data
        job = self._wait_for_done(data['job_id']) or {}
        assert job.get('status') == 'done', job
        result = job.get('result') or {}
        assert 'draft_text' in result, result

    def test_async_format_job_succeeds(self):
        r_any = cast(
            Any,
            self.api.post(
                '/api/ai/format',
                {'proposal_id': self.proposal.id, 'template_hint': 'standard'},
                format='json',
                HTTP_X_ORG_ID=str(self.org.id),
            ),
        )
        assert r_any.status_code == 200
        data = r_any.json()
        assert 'job_id' in data
        job = self._wait_for_done(data['job_id']) or {}
        assert job.get('status') == 'done', job
        result = job.get('result') or {}
        assert 'formatted_text' in result, result
