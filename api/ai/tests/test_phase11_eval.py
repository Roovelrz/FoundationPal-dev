import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase


class Phase11EvalCommandTests(TestCase):
    def test_command_emits_independent_small_eval_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            call_command('run_phase11_eval', output_dir=directory)
            summary = Path(directory) / 'phase11-summary.json'
            self.assertTrue(summary.exists())
            for name in ('rule_rag', 'user_evidence_rag', 'intake_grill', 'end_to_end'):
                self.assertTrue((Path(directory) / f'phase11-{name}.json').exists())
