from django.core.management import call_command
from django.test import TestCase

from ai.ingestion import create_resource_with_chunks
from ai.models import AIChunk, AIResource, EvidenceFact, UserEvidence, WorkflowRun
from ai.query_router import _context_budget, persist_dual_retrieval_trace
from ai.writer_evidence import retrieve_writer_evidence


class DualWriterEvidenceTests(TestCase):
    def _user_evidence(self):
        resource = create_resource_with_chunks(
            type_='team_profile', title='Team profile', source_url='',
            full_text='团队参与了已完成的科研项目。', organization_id='1',
            knowledge_domain='user_evidence',
        )
        AIResource.objects.filter(pk=resource.pk).update(classification_status='classified')
        AIChunk.objects.filter(resource=resource).update(knowledge_domain='user_evidence', index_namespace='user_evidence')
        resource.refresh_from_db()
        chunk = resource.chunks.get()
        return UserEvidence.objects.create(resource=resource, chunk=chunk, organization_id='1')

    def test_writer_retrieval_keeps_rule_and_user_evidence_separate(self):
        evidence = self._user_evidence()
        contexts = retrieve_writer_evidence('summary', {}, organization_id='1')
        self.assertEqual(contexts.rule_candidates, [])
        self.assertEqual(contexts.user_evidence_candidates[0]['chunk_id'], evidence.chunk_id)
        self.assertIn('grant_pack_required', contexts.result.requirement_gaps)

    def test_extraction_creates_review_required_fact_and_trace(self):
        self._user_evidence()
        call_command('extract_user_evidence_facts', organization_id='1')
        fact = EvidenceFact.objects.get()
        self.assertEqual(fact.verification_status, 'extracted')
        contexts = retrieve_writer_evidence('summary', {}, organization_id='1')
        run = WorkflowRun.objects.create(org_id='1')
        persist_dual_retrieval_trace(run, contexts.result)
        run.refresh_from_db()
        self.assertEqual(run.trace_json[-1]['node'], 'dual_retrieval')
        self.assertEqual(run.trace_json[-1]['user_evidence_candidate_count'], 1)
        self.assertIn('normative_query', run.trace_json[-1])
        self.assertIn('factual_query', run.trace_json[-1])

    def test_evidence_result_keeps_structured_fact_and_adjacent_evidence_separate(self):
        evidence = self._user_evidence()
        fact = EvidenceFact.objects.create(
            user_evidence=evidence, subject='team', predicate='accuracy', object='result', fact_type='experiment',
            numeric_value=95, unit='percent', metric_definition='top1_accuracy', author_order=1,
            project_status='completed', authority_level='user_confirmed', verification_status='user_confirmed',
        )
        contexts = retrieve_writer_evidence('summary', {}, organization_id='1')

        returned = contexts.result.user_evidence_results['results'][0]['facts'][0]
        self.assertEqual(returned['fact_id'], fact.id)
        self.assertEqual(returned['unit'], 'percent')
        self.assertEqual(returned['author_order'], 1)
        self.assertEqual(contexts.result.context_budget['domain_scores_not_comparable'], True)

    def test_context_budget_keeps_two_per_domain_and_only_one_flexible_slot(self):
        rule = {'results': [{'requirement_id': value} for value in (1, 2, 3)]}
        evidence = {'results': [{'user_evidence_id': value} for value in (11, 12, 13)]}

        budget = _context_budget(rule, evidence)

        self.assertEqual(budget['rule_context_ids'], [1, 2, 3])
        self.assertEqual(budget['evidence_context_ids'], [11, 12])
        self.assertEqual(budget['flexible_context_domain'], 'grant_rule')
        self.assertEqual(len(budget['rule_context_ids']) + len(budget['evidence_context_ids']), 5)
