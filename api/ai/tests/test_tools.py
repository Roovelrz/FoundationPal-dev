from django.contrib.auth import get_user_model
from django.test import TestCase

from ai.models import ToolInvocation
from ai.services import promote_service
from ai.tools import execute_tool
from ai.workflow import resolve_run_id
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


class ToolExecutionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tool-user', password='pass')
        self.org = Organization.objects.create(name='Tool Org', admin=self.user)
        self.proposal = Proposal.objects.create(author=self.user, org=self.org)
        self.section = ProposalSection.objects.create(proposal=self.proposal, key='intro', title='Introduction')
        self.run_id = str(resolve_run_id(None, proposal_id=self.proposal.id, org_id=str(self.org.id)))
        other_org = Organization.objects.create(name='Other Org', admin=self.user)
        self.other_proposal = Proposal.objects.create(author=self.user, org=other_org)

    def save_arguments(self, key='save-1'):
        return {
            'proposal_id': self.proposal.id,
            'section_id': 'intro',
            'draft_markdown': 'Tool saved draft',
            'answers': {'goal': 'verify'},
            'idempotency_key': key,
        }

    def test_legal_draft_call_is_audited_and_idempotent(self):
        first = execute_tool(
            schema_version='v1', tool_name='save_section_draft', arguments=self.save_arguments(),
            caller_role='writer', caller=self.user, organization_id=str(self.org.id), run_id=self.run_id,
        )
        second = execute_tool(
            schema_version='v1', tool_name='save_section_draft', arguments=self.save_arguments(),
            caller_role='writer', caller=self.user, organization_id=str(self.org.id), run_id=self.run_id,
        )
        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(ToolInvocation.objects.filter(tool_name='save_section_draft').count(), 1)
        invocation = ToolInvocation.objects.get(tool_name='save_section_draft')
        self.assertEqual(invocation.caller, self.user)
        self.assertEqual(str(invocation.workflow_run.run_id), self.run_id)
        self.assertEqual(invocation.replay_count, 1)
        self.assertGreaterEqual(invocation.duration_ms, 0)
        self.section.refresh_from_db()
        self.assertEqual(self.section.draft_content, 'Tool saved draft')

    def test_invalid_schema_is_rejected(self):
        arguments = self.save_arguments()
        arguments['unexpected'] = True
        result = execute_tool(
            schema_version='v1', tool_name='save_section_draft', arguments=arguments,
            caller_role='writer', caller=self.user, organization_id=str(self.org.id), run_id=self.run_id,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error.error_code, 'invalid_tool_input')
        self.assertFalse(ToolInvocation.objects.exists())

    def test_unauthorized_role_is_rejected(self):
        result = execute_tool(
            schema_version='v1', tool_name='save_section_draft', arguments=self.save_arguments(),
            caller_role='planner', caller=self.user, organization_id=str(self.org.id), run_id=self.run_id,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error.error_code, 'tool_not_authorized')
        invocation = ToolInvocation.objects.get(status='rejected')
        self.assertEqual(invocation.error_code, 'tool_not_authorized')
        self.assertEqual(str(invocation.workflow_run.run_id), self.run_id)

    def test_cross_workspace_access_is_rejected(self):
        arguments = self.save_arguments()
        arguments['proposal_id'] = self.other_proposal.id
        result = execute_tool(
            schema_version='v1', tool_name='save_section_draft', arguments=arguments,
            caller_role='writer', caller=self.user, organization_id=str(self.org.id), run_id=self.run_id,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error.error_code, 'workspace_forbidden')

    def test_submit_review_is_idempotent(self):
        arguments = {
            'proposal_id': self.proposal.id,
            'section_id': 'intro',
            'review': {
                'schema_version': 'v1', 'section_key': 'intro', 'decision': 'approve',
                'issues': [], 'required_changes': [], 'protected_facts': [], 'evidence_gaps': [],
            },
            'idempotency_key': 'review-1',
        }
        for _ in range(2):
            result = execute_tool(
                schema_version='v1', tool_name='submit_review', arguments=arguments,
                caller_role='reviewer', caller=self.user, organization_id=str(self.org.id), run_id=self.run_id,
            )
            self.assertTrue(result.success)
        self.assertEqual(ToolInvocation.objects.filter(tool_name='submit_review').count(), 1)

    def test_export_retry_reuses_one_audited_invocation(self):
        self.section.draft_content = 'Approved content'
        self.section.save(update_fields=['draft_content'])
        promote_service(section=self.section)
        arguments = {
            'proposal_id': self.proposal.id,
            'format': 'md',
            'idempotency_key': 'export-1',
        }
        for _ in range(2):
            result = execute_tool(
                schema_version='v1', tool_name='export_proposal', arguments=arguments,
                caller_role='user', caller=self.user, organization_id=str(self.org.id), run_id=self.run_id,
            )
            self.assertTrue(result.success)
            self.assertEqual(result.data['markdown'], '# Proposal\n\n## Introduction\nApproved content')
        self.assertEqual(ToolInvocation.objects.filter(tool_name='export_proposal').count(), 1)
