from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from ai.models import AIChunk, AIResource, EvidenceUsage, HumanApprovalTask, ToolInvocation, WorkflowRun
from ai.workflow import resolve_run_id
from orgs.models import Organization
from proposals.models import Proposal


class RunTimelineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='timeline-user', password='p')
        self.org = Organization.objects.create(name='timeline-org', admin=self.user)
        self.proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        self.run_id = resolve_run_id(None, proposal_id=self.proposal.id, org_id=str(self.org.id))
        self.run = WorkflowRun.objects.get(run_id=self.run_id)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_timeline_aggregates_observability_without_evidence_text(self):
        resource = AIResource.objects.create(
            organization_id=str(self.org.id),
            source_type='guideline',
            sha256='a' * 64,
        )
        chunk = AIChunk.objects.create(
            resource=resource,
            stable_chunk_id='chunk-1',
            chunk_index=0,
            text='sensitive evidence text',
        )
        EvidenceUsage.objects.create(
            workflow_run=self.run,
            chunk=chunk,
            role='writer',
            rank=1,
            similarity_score=0.9,
            used_in_prompt=True,
            cited_by_model=True,
            evidence_alias='E1',
            snapshot_text='sensitive evidence text',
        )
        ToolInvocation.objects.create(
            tool_name='search_guideline',
            caller_role='planner',
            caller=self.user,
            organization_id=str(self.org.id),
            proposal_id=self.proposal.id,
            workflow_run=self.run,
            idempotency_key='timeline-tool',
            status='error',
            error_code='tool_failed',
        )
        HumanApprovalTask.objects.create(
            workflow_run=self.run,
            proposal_id=self.proposal.id,
            thread_id='timeline-thread',
            node='reviewer',
        )

        response = self.api.get(f'/api/ai/runs/{self.run_id}')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['schema_version'], 'v1')
        self.assertEqual(payload['summary']['evidence_count'], 1)
        self.assertEqual(payload['summary']['evidence_used_in_prompt_count'], 1)
        self.assertEqual(payload['summary']['evidence_cited_by_model_count'], 1)
        self.assertEqual(payload['summary']['tool_call_count'], 1)
        self.assertEqual(payload['summary']['tool_error_count'], 1)
        self.assertEqual(payload['summary']['pending_human_task_count'], 1)
        self.assertEqual(payload['evidence'][0]['evidence_alias'], 'E1')
        self.assertNotIn('snapshot_text', payload['evidence'][0])

    def test_timeline_is_hidden_from_another_organization(self):
        other_user = get_user_model().objects.create_user(username='timeline-other', password='p')
        self.api.force_authenticate(other_user)

        response = self.api.get(f'/api/ai/runs/{self.run_id}')

        self.assertEqual(response.status_code, 404)
