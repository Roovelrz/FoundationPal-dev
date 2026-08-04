import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from ai.models import HumanApprovalTask, WorkflowRun
from ai.providers.base import AIResult
from orgs.models import Organization, OrgUser
from proposals.models import Proposal, ProposalSection


@override_settings(DEBUG=True, AI_PROVIDER='stub')
class SectionPreReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='pre-review-user', password='p')
        self.org = Organization.objects.create(name='Pre Review Org', admin=self.user)
        OrgUser.objects.create(org=self.org, user=self.user, role='admin')
        self.proposal = Proposal.objects.create(
            author=self.user,
            org=self.org,
            content={'meta': {'application_system': 'provincial'}},
        )
        self.section = ProposalSection.objects.create(
            proposal=self.proposal,
            key='summary',
            title='项目摘要',
            draft_content='本章说明地方产业需求，并提出阶段目标。',
        )
        self.run = WorkflowRun.objects.create(proposal_id=self.proposal.id, org_id=str(self.org.id))
        self.task = HumanApprovalTask.objects.create(
            workflow_run=self.run,
            proposal_id=self.proposal.id,
            thread_id='pre-review-task',
            node='section_approval',
            input_json={'section_key': self.section.key, 'section_title': self.section.title},
        )
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.headers = {'HTTP_X_ORG_ID': str(self.org.id)}

    @patch('ai.views.get_provider')
    def test_pre_review_can_be_accepted_and_dismissed(self, get_provider):
        get_provider.return_value.pre_review.return_value = AIResult(text=json.dumps({
            'summary': '章节定位明确。',
            'strengths': ['已说明地方需求。'],
            'issues': [{
                'problem': '阶段目标不够具体。',
                'reason': '草稿未列出量化节点。',
                'direction': '补充可验收的阶段指标。',
            }],
        }, ensure_ascii=False))

        response = self.api.post(
            f'/api/ai/human-tasks/{self.task.id}/pre-review',
            {},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['model_output']['pre_review']['summary'], '章节定位明确。')
        self.assertEqual(response.json()['model_output']['pre_review_status'], 'pending')
        self.assertEqual(response.json()['model_output']['pre_review_request_count'], 1)
        self.assertEqual(get_provider.return_value.pre_review.call_args.kwargs['application_system'], 'provincial')

        repeated = self.api.post(
            f'/api/ai/human-tasks/{self.task.id}/pre-review',
            {},
            format='json',
            **self.headers,
        )
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertEqual(repeated.json()['model_output']['pre_review_request_count'], 2)

        accepted = self.api.post(
            f'/api/ai/human-tasks/{self.task.id}/pre-review',
            {'action': 'accept'},
            format='json',
            **self.headers,
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(accepted.json()['model_output']['pre_review_status'], 'accepted')

        dismissed = self.api.post(
            f'/api/ai/human-tasks/{self.task.id}/pre-review',
            {'action': 'dismiss'},
            format='json',
            **self.headers,
        )
        self.assertEqual(dismissed.status_code, 200, dismissed.content)
        self.assertNotIn('pre_review', dismissed.json()['model_output'])
