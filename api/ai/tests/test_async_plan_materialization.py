from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from unittest.mock import patch

from ai.models import AIJob
from ai.tasks import run_plan
from proposals.models import ProposalSection


class AsyncPlanMaterializationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='asyncplanner', password='p')

    def _create_proposal(self):
        # Use API to ensure org auto-provision path stays covered
        self.client.force_login(self.user)
        resp = self.client.post(
            '/api/proposals/',
            data={'content': {'title': 'Base Title'}},
            content_type='application/json',
        )
        assert resp.status_code in (200, 201), resp.content
        return resp.json()['id']

    def test_run_plan_creates_sections_and_persists_keys(self):
        pid = self._create_proposal()
        blueprint = [
            {'section_key': 'Background', 'title': 'Background', 'questions': ['Why does it matter?']},
            {'section_key': 'Approach', 'title': 'Approach', 'questions': ['How will it work?']},
        ]
        # Create pending job
        job = AIJob.objects.create(
            type='plan',
            input_json={'proposal_id': pid, 'grant_url': 'https://example.com', 'text_spec': 'Spec'},
            created_by=self.user,
            org_id='',  # personal scope
        )
        with patch('ai.tasks._provider') as prov, patch('ai.tasks.retrieval.retrieve_for_plan', return_value=[]):
            prov.return_value.plan.return_value = {'schema_version': 'v1', 'sections': blueprint}
            run_plan(job.id)  # type: ignore[attr-defined]
        job.refresh_from_db()
        self.assertEqual(job.status, 'done')
        # result_json is a JSONField; runtime ensures dict when status=='done'
        self.assertIsNotNone(job.result_json)
        self.assertNotIn('plan', job.result_json)  # type: ignore[operator]
        self.assertEqual(job.result_json['schema_version'], 'v1')  # type: ignore[index]
        self.assertEqual(job.result_json['sections'], blueprint)  # type: ignore[index]
        self.assertIn('created_sections', job.result_json)  # type: ignore[operator]
        self.assertEqual(set(job.result_json['created_sections']), {'background', 'approach'})  # type: ignore[index]
        keys = list(ProposalSection.objects.filter(proposal_id=pid).order_by('order').values_list('key', flat=True))
        self.assertEqual(keys, ['background', 'approach'])
        bg = ProposalSection.objects.get(proposal_id=pid, key='background')

    @override_settings(AI_ASYNC=1, CELERY_BROKER_URL='memory://')
    def test_plan_endpoint_persists_request_proposal_id_in_job(self):
        pid = self._create_proposal()

        with patch('ai.views.run_plan.delay') as delay:
            resp = self.client.post(
                '/api/ai/plan',
                data={'proposal_id': pid, 'text_spec': 'Spec'},
                content_type='application/json',
            )

        self.assertEqual(resp.status_code, 200)
        job = AIJob.objects.get(id=resp.json()['job_id'])
        self.assertEqual(job.input_json['proposal_id'], pid)
        delay.assert_called_once_with(job.id)
