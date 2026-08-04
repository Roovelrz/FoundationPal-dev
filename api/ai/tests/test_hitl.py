from django.contrib.auth import get_user_model
from django.test import TestCase
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection

from ai.hitl import build_human_graph


class HumanInTheLoopTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='hitl-user', password='p')
        self.org = Organization.objects.create(name='hitl-org', admin=self.user)
        self.proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        self.section = ProposalSection.objects.create(
            proposal=self.proposal,
            key='summary',
            title='摘要',
            draft_content='待审批草稿',
        )
        self.client.force_login(self.user)

    def _create_section_task(self, thread_id):
        response = self.client.post('/api/ai/human-tasks', {
            'proposal_id': self.proposal.id,
            'node': 'section_approval',
            'thread_id': thread_id,
            'input': {
                'section_key': self.section.key,
                'section_title': self.section.title,
                'draft_summary': self.section.draft_content,
            },
            'model_output': {'review_summary': '审查结论：approve'},
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_inmemory_graph_pauses_and_resumes_after_graph_rebuild(self):
        saver = InMemorySaver()
        config = {'configurable': {'thread_id': 'thread-approve'}}
        build_human_graph(saver).invoke({
            'thread_id': 'thread-approve',
            'human_node': 'section_approval',
            'human_input': {'draft': '草稿'},
            'model_output': {'review': '通过'},
        }, config)
        paused = build_human_graph(saver).get_state(config)
        self.assertEqual(paused.values['human_node'], 'section_approval')
        result = build_human_graph(saver).invoke(Command(resume={'action': 'approve'}), config)
        self.assertEqual(result['status'], 'approved')

    def test_edit_reenters_validation_and_reject_is_not_success(self):
        saver = InMemorySaver()
        graph = build_human_graph(saver)
        config = {'configurable': {'thread_id': 'thread-edit'}}
        graph.invoke({'thread_id': 'thread-edit', 'human_node': 'budget_confirmation'}, config)
        result = graph.invoke(Command(resume={'action': 'edit', 'edited_input': {'budget': '10万'}}), config)
        self.assertEqual(result['status'], 'ready_after_edit')
        config = {'configurable': {'thread_id': 'thread-reject'}}
        graph.invoke({'thread_id': 'thread-reject', 'human_node': 'final_export_confirmation'}, config)
        result = graph.invoke(Command(resume={'action': 'reject'}), config)
        self.assertEqual(result['status'], 'rejected')

    def test_api_persists_pending_task_and_blocks_duplicate_decision(self):
        response = self.client.post('/api/ai/human-tasks', {
            'proposal_id': self.proposal.id,
            'node': 'plan_confirmation',
            'input': {'plan': '章节方案'},
            'model_output': {'sections': 3},
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        task = response.json()
        listed = self.client.get(f'/api/ai/human-tasks?proposal_id={self.proposal.id}')
        self.assertEqual(listed.json()['tasks'][0]['thread_id'], task['thread_id'])
        decision = self.client.post(f"/api/ai/human-tasks/{task['id']}/decision", {
            'thread_id': task['thread_id'], 'action': 'approve',
        }, content_type='application/json')
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()['status'], 'approved')
        duplicate = self.client.post(f"/api/ai/human-tasks/{task['id']}/decision", {
            'thread_id': task['thread_id'], 'action': 'approve',
        }, content_type='application/json')
        self.assertEqual(duplicate.status_code, 409)

    def test_section_approval_locks_section_without_generating_final_draft(self):
        task = self._create_section_task('section-approve')
        decision = self.client.post('/api/ai/human-tasks/' + str(task['id']) + '/decision', {
            'thread_id': task['thread_id'],
            'action': 'approve',
        }, content_type='application/json')
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()['status'], 'approved')
        self.section.refresh_from_db()
        self.assertTrue(self.section.locked)
        self.assertEqual(self.section.state, 'approved')
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.final_markdown, '')
        duplicate = self.client.post('/api/ai/human-tasks/' + str(task['id']) + '/decision', {
            'thread_id': task['thread_id'],
            'action': 'approve',
        }, content_type='application/json')
        self.assertEqual(duplicate.status_code, 409)

    def test_section_edit_and_reject_keep_draft_unlocked(self):
        edit_task = self._create_section_task('section-edit')
        edit = self.client.post('/api/ai/human-tasks/' + str(edit_task['id']) + '/decision', {
            'thread_id': edit_task['thread_id'],
            'action': 'edit',
        }, content_type='application/json')
        self.assertEqual(edit.status_code, 200)
        self.assertEqual(edit.json()['status'], 'ready_after_edit')
        self.section.refresh_from_db()
        self.assertFalse(self.section.locked)
        self.assertEqual(self.section.state, 'draft')

        reject_task = self._create_section_task('section-reject')
        reject = self.client.post('/api/ai/human-tasks/' + str(reject_task['id']) + '/decision', {
            'thread_id': reject_task['thread_id'],
            'action': 'reject',
        }, content_type='application/json')
        self.assertEqual(reject.status_code, 200)
        self.assertEqual(reject.json()['status'], 'rejected')
        self.section.refresh_from_db()
        self.assertFalse(self.section.locked)
        self.assertEqual(self.section.state, 'draft')
