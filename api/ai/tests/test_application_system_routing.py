import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from ai.models import AIJob
from ai.providers.base import AIResult
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


@override_settings(AI_ASYNC=False)
class ApplicationSystemRoutingTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='application-system', password='p')
        self.org = Organization.objects.create(name='application-system-org', admin=self.user)
        self.proposal = Proposal.objects.create(
            author=self.user,
            org=self.org,
            content={
                'meta': {'title': '校级项目', 'application_system': 'university'},
                'sections': {},
            },
        )
        self.section = ProposalSection.objects.create(
            proposal=self.proposal,
            key='section-a',
            title='Section A',
            draft_content='原始草稿',
        )
        self.client.force_login(self.user)

    def test_sync_ai_endpoints_use_the_project_application_system(self):
        blueprint = [
            {
                'section_key': self.section.key,
                'title': 'Planned Section',
                'questions': ['What is the objective?'],
            },
        ]
        writer_payload = json.dumps({
            'schema_version': 'v1',
            'section_key': self.section.key,
            'draft_markdown': '撰写后的草稿',
            'evidence_ids': [],
            'warnings': [],
            'missing_evidence': [],
        })

        with patch('ai.views.get_provider') as provider_factory:
            provider = provider_factory.return_value
            provider.plan.return_value = {'schema_version': 'v1', 'sections': blueprint}
            response = self.client.post(
                '/api/ai/plan',
                data={'proposal_id': self.proposal.id, 'text_spec': '测试方向'},
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(provider.plan.call_args.kwargs['application_system'], 'university')

            provider.write.return_value = AIResult(text=writer_payload, model_id='test-model')
            response = self.client.post(
                '/api/ai/write',
                data={
                    'proposal_id': self.proposal.id,
                    'section_id': self.section.key,
                    'answers': {'目标': '完成校内验证'},
                },
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(provider.write.call_args.kwargs['application_system'], 'university')

            provider.revise.return_value = AIResult(text='修订后的草稿', model_id='test-model')
            response = self.client.post(
                '/api/ai/revise',
                data={
                    'proposal_id': self.proposal.id,
                    'section_id': self.section.key,
                    'base_text': '撰写后的草稿',
                    'change_request': '补充实施节点',
                },
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(provider.revise.call_args.kwargs['application_system'], 'university')

            self.section.refresh_from_db()
            self.section.state = 'approved'
            self.section.locked = True
            self.section.content = self.section.draft_content
            self.section.approved_content = self.section.draft_content
            self.section.save(update_fields=['state', 'locked', 'content', 'approved_content', 'updated_at'])
            content = dict(self.proposal.content or {})
            meta = dict(content.get('meta') or {})
            meta['full_draft_review'] = {'status': 'approved', 'version': 1}
            content['meta'] = meta
            self.proposal.content = content
            self.proposal.save(update_fields=['content'])

            provider.format_final.return_value = AIResult(text='定稿内容', model_id='test-model')
            response = self.client.post(
                '/api/ai/format',
                data={'proposal_id': self.proposal.id},
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(provider.format_final.call_args.kwargs['application_system'], 'university')

    @override_settings(AI_ASYNC=True, CELERY_BROKER_URL='memory://')
    def test_async_plan_job_keeps_the_project_application_system(self):
        with patch('ai.views.run_plan.delay'):
            response = self.client.post(
                '/api/ai/plan',
                data={'proposal_id': self.proposal.id, 'text_spec': '测试方向'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        job = AIJob.objects.get(id=response.json()['job_id'])
        self.assertEqual(job.input_json['application_system'], 'university')
