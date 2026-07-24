import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from ai.models import AIMetric, ToolInvocation
from ai.observability import build_phase10_report
from ai.workflow import resolve_run_id


class Phase10ObservabilityTests(TestCase):
    def test_report_uses_persisted_tool_and_workflow_records(self):
        run_id = resolve_run_id(None, org_id='scope-a')
        from ai.models import WorkflowRun

        workflow_run = WorkflowRun.objects.get(run_id=run_id)
        workflow_run.architecture = 'multi_agent'
        workflow_run.status = 'awaiting_human_approval'
        workflow_run.handoffs_json = [{'agent': 'reviewer'}]
        workflow_run.revision_count = 1
        workflow_run.save()
        ToolInvocation.objects.create(
            tool_name='search_guideline', caller_role='planner', organization_id='scope-a',
            workflow_run=workflow_run, status='done', duration_ms=12, replay_count=1,
        )

        report = build_phase10_report(organization_id='scope-a')

        self.assertEqual(report['scope']['run_count'], 1)
        self.assertEqual(report['tools']['tool_call_success_rate'], 1.0)
        self.assertEqual(report['tools']['idempotent_retry_success_rate'], 1.0)
        self.assertEqual(report['workflow_and_agents']['multi_agent']['workflow_task_success_rate'], 1.0)
        self.assertEqual(report['workflow_and_agents']['multi_agent']['reviewer_regression_rate'], 1.0)

    def test_report_aggregates_persisted_estimated_cost(self):
        AIMetric.objects.create(
            type='evaluation', model_id='deepseek-v4-pro', org_id='scope-cost',
            tokens_used=100, estimated_cost_usd=0.01234567,
        )

        report = build_phase10_report(organization_id='scope-cost')

        self.assertEqual(report['cost']['token_usage'], 100)
        self.assertEqual(report['cost']['estimated_cost_usd'], 0.01234567)

    def test_command_writes_a_frozen_case_set_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cases = root / 'cases.json'
            cases.write_text(json.dumps({'cases': [{'case_id': 'one'}]}), encoding='utf-8')
            call_command('run_phase10_report', '--output-dir', str(root), '--frozen-cases', str(cases))
            payload = json.loads((root / 'phase10-eval.json').read_text(encoding='utf-8'))
        self.assertEqual(payload['frozen_case_set']['count'], 1)
        self.assertEqual(len(payload['frozen_case_set']['sha256']), 64)
