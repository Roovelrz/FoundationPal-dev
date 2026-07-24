from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection

from ai.proposal_graph import run_proposal_graph
from ai.models import WorkflowRun


def review(decision):
    return {
        'schema_version': 'v1',
        'section_key': 'summary',
        'decision': decision,
        'issues': [],
        'required_changes': [],
        'protected_facts': [],
        'evidence_gaps': [],
    }


class ProposalGraphTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='graph-user', password='p')
        org = Organization.objects.create(name='graph-org', admin=user)
        self.proposal = Proposal.objects.create(author=user, org=org, content={})
        self.section = ProposalSection.objects.create(proposal=self.proposal, key='summary', title='摘要')
        self.state = {
            'run_id': 'graph-run-1',
            'thread_id': 'proposal-1',
            'organization_id': str(org.id),
            'proposal_id': self.proposal.id,
            'section_key': self.section.key,
            'plan': [{'section_key': 'summary', 'title': '摘要', 'questions': ['目标是什么']}],
            'answers': {'目标': '验证图编排'},
            'evidence_ids': [],
            'draft': '初始草稿',
        }

    def test_approve_path_stops_for_human_approval(self):
        result = run_proposal_graph({**self.state, 'review': review('approve')})
        self.assertEqual(result['status'], 'awaiting_human_approval')
        self.assertEqual([item['node'] for item in result['trace']], ['planner', 'writer:0', 'reviewer:0', 'human'])
        self.section.refresh_from_db()
        self.assertEqual(self.section.draft_content, '初始草稿')

    def test_rewrite_routes_back_to_writer(self):
        result = run_proposal_graph({**self.state, 'review_queue': [review('rewrite'), review('approve')]})
        nodes = [item['node'] for item in result['trace']]
        self.assertEqual(nodes, ['planner', 'writer:0', 'reviewer:0', 'writer:1', 'reviewer:1', 'human'])
        self.assertEqual(result['revision_count'], 1)

    def test_human_review_stops_without_finalizing(self):
        result = run_proposal_graph({**self.state, 'review': review('human_review')})
        self.assertEqual(result['status'], 'awaiting_human_approval')
        self.assertNotIn('finalize', [item['node'] for item in result['trace']])

    def test_rewrite_limit_routes_to_human(self):
        result = run_proposal_graph({**self.state, 'max_revisions': 1, 'review': review('rewrite')})
        self.assertEqual(result['status'], 'awaiting_human_approval')
        self.assertEqual([item['node'] for item in result['trace']], ['planner', 'writer:0', 'reviewer:0', 'human'])

    def test_writer_failure_retries_once_then_continues(self):
        from ai import proposal_graph

        original = proposal_graph.write_service
        with patch('ai.proposal_graph.write_service', side_effect=[RuntimeError('temporary'), original]):
            result = run_proposal_graph({**self.state, 'review': review('approve')})
        writer_nodes = [item for item in result['trace'] if item['node'].startswith('writer')]
        self.assertEqual([item['status'] for item in writer_nodes], ['failed', 'completed'])

    def test_same_input_does_not_create_duplicate_sections(self):
        state = {**self.state, 'review': review('approve')}
        run_proposal_graph(state)
        run_proposal_graph(state)
        self.assertEqual(ProposalSection.objects.filter(proposal=self.proposal, key='summary').count(), 1)

    def test_finalize_only_runs_after_existing_human_approval(self):
        self.section.approved_content = '已审批内容'
        self.section.state = 'approved'
        self.section.locked = True
        self.section.save()
        result = run_proposal_graph({**self.state, 'resume_after_approval': True})
        self.assertEqual(result['status'], 'completed')
        self.assertIn('已审批内容', result['final_markdown'])

    def test_auto_approve_completes_without_human_intervention(self):
        result = run_proposal_graph({**self.state, 'review': review('approve'), 'auto_approve': True})
        self.assertEqual(result['status'], 'completed')
        self.section.refresh_from_db()
        self.assertTrue(self.section.locked)

    def test_workflow_endpoint_returns_trace_for_accessible_proposal(self):
        self.client.force_login(self.proposal.author)
        response = self.client.post(
            '/api/ai/workflow/run',
            data={**self.state, 'review': review('approve')},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'awaiting_human_approval')
        self.assertEqual(response.json()['trace'][-1]['node'], 'human')
        run = WorkflowRun.objects.get(run_id=response.json()['run_id'])
        self.assertEqual(run.architecture, 'multi_agent')
        self.assertEqual(run.status, 'awaiting_human_approval')
        self.assertEqual(run.trace_json[-1]['node'], 'human')
        self.assertEqual(run.fallback_mode, 'human')
