from django.contrib.auth import get_user_model
from django.test import TestCase
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


class GrillApiTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='grill-user', password='p')
        org = Organization.objects.create(name='grill-org', admin=user)
        self.proposal = Proposal.objects.create(author=user, org=org, content={})
        self.section = ProposalSection.objects.create(
            proposal=self.proposal, key='summary', title='摘要', draft_content='原始草稿'
        )
        self.client.force_login(user)

    def test_planning_session_is_bounded_and_persisted(self):
        response = self.client.get(f'/api/ai/grill?proposal_id={self.proposal.id}&mode=planning')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['max_questions'], 5)
        for _ in range(5):
            response = self.client.post(
                '/api/ai/grill',
                data={'proposal_id': self.proposal.id, 'mode': 'planning', 'answers': {}, 'skip': True},
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['completion_reason'], 'all_questions_completed')
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.content['grill']['planning']['question_count'], 5)

    def test_revision_finish_returns_suggestion_without_changing_draft(self):
        self.client.get(
            f'/api/ai/grill?proposal_id={self.proposal.id}&mode=revision&section_key={self.section.key}'
        )
        response = self.client.post(
            '/api/ai/grill',
            data={
                'proposal_id': self.proposal.id,
                'mode': 'revision',
                'section_key': self.section.key,
                'answers': {'change_goal': '强化创新性'},
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/api/ai/grill',
            data={'proposal_id': self.proposal.id, 'mode': 'revision', 'section_key': self.section.key, 'finish': True},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('强化创新性', response.json()['suggestion'])
        self.section.refresh_from_db()
        self.assertEqual(self.section.draft_content, '原始草稿')

    def test_planning_session_can_return_to_the_previous_question(self):
        self.client.get(f'/api/ai/grill?proposal_id={self.proposal.id}&mode=planning')
        response = self.client.post(
            '/api/ai/grill',
            data={
                'proposal_id': self.proposal.id,
                'mode': 'planning',
                'answers': {'funding_category': '青年基金', 'research_direction': '智能信号处理'},
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['question']['index'], 2)

        response = self.client.post(
            '/api/ai/grill',
            data={
                'proposal_id': self.proposal.id,
                'mode': 'planning',
                'answers': {'core_problem': '提高跨场景泛化能力'},
                'previous': True,
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['question']['index'], 1)
        self.assertEqual(response.json()['collected_answers']['core_problem'], '提高跨场景泛化能力')

    def test_plan_receives_only_confirmed_answers(self):
        from unittest.mock import patch

        self.client.get(f'/api/ai/grill?proposal_id={self.proposal.id}&mode=planning')
        self.client.post(
            '/api/ai/grill',
            data={
                'proposal_id': self.proposal.id,
                'mode': 'planning',
                'answers': {'funding_category': '青年基金', 'research_direction': '智能信号处理'},
            },
            content_type='application/json',
        )
        with patch('ai.views.get_provider') as factory:
            response = self.client.post('/api/ai/plan', data={'proposal_id': self.proposal.id}, content_type='application/json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error'], 'grill_confirmation_required')
        self.client.post(
            '/api/ai/grill',
            data={'proposal_id': self.proposal.id, 'mode': 'planning', 'finish': True, 'confirm': True},
            content_type='application/json',
        )
        with patch('ai.views.get_provider') as factory:
            factory.return_value.plan.return_value = {
                'schema_version': 'v1',
                'sections': [{'section_key': 'summary', 'title': '摘要', 'questions': ['请概述研究目标']}],
            }
            response = self.client.post('/api/ai/plan', data={'proposal_id': self.proposal.id}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('funding_category: 青年基金', factory.return_value.plan.call_args.kwargs['text_spec'])

    def test_plan_without_grill_session_is_not_blocked(self):
        from unittest.mock import patch

        with patch('ai.views.get_provider') as factory:
            factory.return_value.plan.return_value = {
                'schema_version': 'v1',
                'sections': [{'section_key': 'summary', 'title': '摘要', 'questions': ['请概述研究目标']}],
            }
            response = self.client.post(
                '/api/ai/plan',
                data={'proposal_id': self.proposal.id},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
