from django.contrib.auth import get_user_model
from django.test import TestCase
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from orgs.models import Organization
from proposals.models import Proposal

from ai.hitl import build_human_graph


class HumanInTheLoopTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='hitl-user', password='p')
        self.org = Organization.objects.create(name='hitl-org', admin=self.user)
        self.proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        self.client.force_login(self.user)

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
