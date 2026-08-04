import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from ai.models import HumanApprovalTask
from ai.providers.base import AIResult
from orgs.models import Organization, OrgUser
from proposals.models import Proposal, ProposalSection


@override_settings(DEBUG=True, AI_PROVIDER='stub')
class FullDraftApprovalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='full-draft-user', password='p')
        self.org = Organization.objects.create(name='Full Draft Org', admin=self.user)
        OrgUser.objects.create(org=self.org, user=self.user, role='admin')
        self.proposal = Proposal.objects.create(
            author=self.user,
            org=self.org,
            content={'meta': {'title': '全文审批测试', 'application_system': 'nsfc'}},
        )
        self.first = ProposalSection.objects.create(
            proposal=self.proposal,
            key='summary',
            title='摘要',
            draft_content='摘要草稿',
            approved_content='摘要草稿',
            state='approved',
            locked=True,
        )
        self.second = ProposalSection.objects.create(
            proposal=self.proposal,
            key='plan',
            title='实施计划',
            draft_content='实施计划草稿',
            approved_content='实施计划草稿',
            state='approved',
            locked=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.headers = {'HTTP_X_ORG_ID': str(self.org.id)}

    def _load_full_draft(self):
        response = self.api.get(f'/api/ai/proposals/{self.proposal.id}/full-draft', **self.headers)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _create_full_task(self, draft):
        response = self.api.post(
            '/api/ai/human-tasks',
            {
                'proposal_id': self.proposal.id,
                'node': 'final_export_confirmation',
                'thread_id': f'full-draft-{self.proposal.id}-{draft["version"]}',
                'input': {
                    'kind': 'full_draft',
                    'draft_title': '审批后全文草稿',
                    'draft_version': draft['version'],
                    'draft_text': draft['draft_text'],
                },
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_full_draft_requires_human_approval_before_formatting(self):
        self._load_full_draft()
        response = self.api.post(
            '/api/ai/format',
            {'proposal_id': self.proposal.id},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['error'], 'full_draft_approval_required')

    def test_finalized_proposal_cannot_regenerate_the_chapter_plan(self):
        self.proposal.final_markdown = '# 已生成最终定稿'
        self.proposal.save(update_fields=['final_markdown'])

        response = self.api.post(
            '/api/ai/plan',
            {'proposal_id': self.proposal.id},
            format='json',
            **self.headers,
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['error'], 'proposal_finalized')

    def test_full_draft_approval_is_persisted(self):
        draft = self._load_full_draft()
        task = self._create_full_task(draft)
        response = self.api.post(
            f'/api/ai/human-tasks/{task["id"]}/decision',
            {'thread_id': task['thread_id'], 'action': 'approve'},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['status'], 'approved')
        self.proposal.refresh_from_db()
        review = self.proposal.content['meta']['full_draft_review']
        self.assertEqual(review['status'], 'approved')
        self.assertEqual(review['version'], draft['version'])

    def test_rejected_full_draft_can_be_submitted_for_a_new_approval(self):
        draft = self._load_full_draft()
        task = self._create_full_task(draft)
        rejected = self.api.post(
            f'/api/ai/human-tasks/{task["id"]}/decision',
            {'thread_id': task['thread_id'], 'action': 'reject'},
            format='json',
            **self.headers,
        )
        self.assertEqual(rejected.status_code, 200, rejected.content)

        retry = self.api.post(
            '/api/ai/human-tasks',
            {
                'proposal_id': self.proposal.id,
                'node': 'final_export_confirmation',
                'thread_id': f'full-draft-{self.proposal.id}-{draft["version"]}-retry',
                'input': {
                    'kind': 'full_draft',
                    'draft_title': '审批后全文草稿',
                    'draft_version': draft['version'],
                    'draft_text': draft['draft_text'],
                },
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(retry.status_code, 201, retry.content)
        self.assertEqual(retry.json()['status'], 'pending')

    @patch('ai.views.get_provider')
    def test_full_draft_reuses_revision_endpoint_before_persisting(self, get_provider):
        get_provider.return_value.revise.return_value = AIResult(text='修订后的全文草稿', model_id='test-model')
        draft = self._load_full_draft()

        response = self.api.post(
            '/api/ai/revise',
            {
                'proposal_id': self.proposal.id,
                'draft_scope': 'full',
                'base_text': draft['draft_text'],
                'change_request': '统一章节衔接。',
            },
            format='json',
            **self.headers,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['draft_text'], '修订后的全文草稿')
        self.assertEqual(get_provider.return_value.revise.call_args.kwargs['application_system'], 'nsfc')

    @patch('ai.views.get_provider')
    def test_revised_full_draft_persists_and_invalidates_pending_approval(self, get_provider):
        get_provider.return_value.revise.return_value = AIResult(text='修订后的全文草稿', model_id='test-model')
        draft = self._load_full_draft()
        task = self._create_full_task(draft)
        revised = self.api.post(
            '/api/ai/revise',
            {
                'proposal_id': self.proposal.id,
                'draft_scope': 'full',
                'base_text': draft['draft_text'],
                'change_request': '补充全文章节衔接。',
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(revised.status_code, 200, revised.content)

        saved = self.api.patch(
            f'/api/ai/proposals/{self.proposal.id}/full-draft',
            {'draft_text': revised.json()['draft_text']},
            format='json',
            **self.headers,
        )

        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(saved.json()['draft_text'], '修订后的全文草稿')
        self.assertEqual(saved.json()['approval_status'], 'draft')
        self.assertGreater(saved.json()['version'], draft['version'])
        self.assertEqual(HumanApprovalTask.objects.get(id=task['id']).status, 'ready_after_edit')

    @patch('ai.views.get_provider')
    def test_full_draft_pre_review_counts_requests_and_reopen_invalidates_it(self, get_provider):
        get_provider.return_value.pre_review.return_value = AIResult(text=json.dumps({
            'summary': '全文结构已经形成。',
            'strengths': ['章节顺序清晰。'],
            'issues': [{
                'problem': '章节衔接仍需加强。',
                'reason': '摘要与实施计划之间缺少过渡说明。',
                'direction': '补充目标到实施路径的衔接段。',
            }],
        }, ensure_ascii=False))
        draft = self._load_full_draft()
        task = self._create_full_task(draft)
        first = self.api.post(
            f'/api/ai/human-tasks/{task["id"]}/pre-review',
            {},
            format='json',
            **self.headers,
        )
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()['model_output']['pre_review_request_count'], 1)
        second = self.api.post(
            f'/api/ai/human-tasks/{task["id"]}/pre-review',
            {},
            format='json',
            **self.headers,
        )
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.json()['model_output']['pre_review_request_count'], 2)

        reopen = self.api.post(f'/api/ai/sections/{self.second.id}/reopen', {}, format='json', **self.headers)
        self.assertEqual(reopen.status_code, 200, reopen.content)
        self.second.refresh_from_db()
        self.assertFalse(self.second.locked)
        self.assertEqual(self.second.state, 'draft')
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.content['meta']['full_draft_review']['status'], 'invalidated')
