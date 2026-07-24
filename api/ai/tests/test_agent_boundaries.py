from django.contrib.auth import get_user_model
from django.test import TestCase
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection

from ai.agent_boundaries import AGENT_TOOLS, supervisor_next_agent, validate_agent_result
from ai.tools import execute_tool


class AgentBoundaryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='agent-user', password='p')
        self.org = Organization.objects.create(name='agent-org', admin=self.user)
        self.proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        self.section = ProposalSection.objects.create(proposal=self.proposal, key='summary', title='摘要')

    def test_agents_have_disjoint_write_and_retrieval_permissions(self):
        self.assertNotIn('save_section_draft', AGENT_TOOLS['planner'])
        self.assertNotIn('promote_section', AGENT_TOOLS['writer'])
        self.assertNotIn('get_team_profile', AGENT_TOOLS['reviewer'])

    def test_supervisor_only_routes_to_fixed_agents(self):
        self.assertEqual(supervisor_next_agent(phase='plan'), 'planner')
        self.assertEqual(supervisor_next_agent(phase='unknown'), 'human')

    def test_each_agent_emits_its_own_schema_handoff(self):
        plan, handoff = validate_agent_result('planner', {'run_id': 'r1', 'plan': [{'section_key': 'summary', 'title': '摘要', 'questions': ['目标']} ]})
        self.assertEqual(plan['schema_version'], 'v1')
        self.assertEqual(handoff['schema_version'], 'ProposalPlan.v1')
        draft, handoff = validate_agent_result('writer', {'run_id': 'r1', 'section_key': 'summary', 'draft': '草稿', 'evidence_ids': []})
        self.assertEqual(draft['missing_evidence'], ['evidence_not_supplied'])
        self.assertEqual(handoff['schema_version'], 'SectionDraft.v1')

    def test_cross_role_tool_calls_are_rejected(self):
        result = execute_tool(
            schema_version='v1', tool_name='save_section_draft', caller_role='planner', caller=self.user,
            organization_id=str(self.org.id), run_id=None,
            arguments={'proposal_id': self.proposal.id, 'section_id': 'summary', 'draft_markdown': 'x', 'answers': {}, 'idempotency_key': 'p1'},
        )
        self.assertFalse(result.success)

    def test_agent_cannot_call_tool_for_another_workspace(self):
        other_user = get_user_model().objects.create_user(username='other-agent', password='p')
        other_org = Organization.objects.create(name='other-agent-org', admin=other_user)
        other_proposal = Proposal.objects.create(author=other_user, org=other_org, content={})
        result = execute_tool(
            schema_version='v1', tool_name='search_guideline', caller_role='planner', caller=self.user,
            organization_id=str(self.org.id), run_id=None,
            arguments={'proposal_id': other_proposal.id, 'query': '指南'},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error.error_code, 'workspace_forbidden')
        result = execute_tool(
            schema_version='v1', tool_name='promote_section', caller_role='writer', caller=self.user,
            organization_id=str(self.org.id), run_id=None,
            arguments={'proposal_id': self.proposal.id, 'section_id': 'summary', 'idempotency_key': 'w1'},
        )
        self.assertFalse(result.success)
        result = execute_tool(
            schema_version='v1', tool_name='get_team_profile', caller_role='reviewer', caller=self.user,
            organization_id=str(self.org.id), run_id=None,
            arguments={'proposal_id': self.proposal.id},
        )
        self.assertFalse(result.success)
