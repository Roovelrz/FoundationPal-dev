import json
from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from ai.ingestion import create_resource_with_chunks
from ai.intake import build_policy, detect_profile, intake_route, start_intake
from ai.phase40_p03 import evaluate_intake_contract
from ai.models import EvidenceFact, GrantPack, GrantPackVersion, GrantProgram, GrillAnswer, ProposalBrief, ProposalDecision, ProposalIntakeProfile, UserEvidence
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


class Phase7IntakeTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='phase7-user', password='p')
        self.org = Organization.objects.create(name='Phase7 Org', admin=user)
        self.proposal = Proposal.objects.create(author=user, org=self.org, content={})
        program = GrantProgram.objects.create(name='Fixture Fund', program_type='fixture', region='CN', authority='Fixture')
        pack = GrantPack.objects.create(program=program, code='fixture-pack', name='Fixture Fund')
        self.verified_version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='published')
        generic_program = GrantProgram.objects.create(name='Generic Fund', program_type='generic', region='CN', authority='Fixture')
        generic_pack = GrantPack.objects.create(program=generic_program, code='generic-pack', name='Generic Fund')
        self.generic_version = GrantPackVersion.objects.create(pack=generic_pack, year=2026, version='v1', status='published')
        self.client.force_login(user)

    def _start(self, task_mode='plan_from_scratch', quality_level='standard'):
        response = self.client.post('/api/ai/intake', data={
            'proposal_id': self.proposal.id, 'task_mode': task_mode, 'quality_level': quality_level,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_intake_creates_versioned_profile_policy_and_single_question(self):
        first = self._start()
        self.assertEqual(first['work_plan_preview']['grill_mode'], 'evidence_confirmation')
        self.assertIsNotNone(first['question_card'])
        self.assertEqual(ProposalIntakeProfile.objects.get().version, 1)
        second = self._start()
        self.assertEqual(ProposalIntakeProfile.objects.order_by('-version').first().version, 2)
        self.assertNotEqual(first['session_id'], second['session_id'])

    def test_answer_is_idempotent_and_consensus_uses_confirmed_decisions(self):
        payload = self._start()
        session_id = payload['session_id']
        card = payload['question_card']
        answer = {'session_id': session_id, 'node_id': card['node_id'], 'action': 'custom', 'answer': '信号识别', 'idempotency_key': 'same-answer'}
        first = self.client.post('/api/ai/intake/grill', data=answer, content_type='application/json')
        self.assertEqual(first.status_code, 200)
        replay = self.client.post('/api/ai/intake/grill', data=answer, content_type='application/json')
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()['idempotent_replay'])
        self.assertEqual(GrillAnswer.objects.count(), 1)
        self.assertEqual(ProposalDecision.objects.count(), 1)
        self.assertEqual(ProposalBrief.objects.get().content['research_object'], '信号识别')

    def test_quick_polish_full_draft_skips_grill(self):
        ProposalSection.objects.create(proposal=self.proposal, key='draft', title='draft', draft_content='x' * 8001)
        payload = self._start(task_mode='polish_existing', quality_level='quick')
        self.assertEqual(payload['status'], 'skipped')
        self.assertIsNone(payload['question_card'])

    def test_standard_mode_cannot_confirm_after_skipping_blocking_decision(self):
        payload = self._start()
        self.client.post('/api/ai/intake/grill', data={
            'session_id': payload['session_id'], 'node_id': payload['question_card']['node_id'],
            'action': 'skip', 'idempotency_key': 'skip-first',
        }, content_type='application/json')
        response = self.client.post('/api/ai/intake/consensus', data={
            'session_id': payload['session_id'], 'confirm': True,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error'], 'blocking_decisions_remaining')

    def test_ten_intake_combinations_use_one_backend_contract(self):
        combinations = [
            ('plan_from_scratch', 'quick'), ('plan_from_scratch', 'standard'), ('plan_from_scratch', 'deep'),
            ('refine_outline', 'quick'), ('refine_outline', 'standard'), ('refine_outline', 'deep'),
            ('polish_existing', 'quick'), ('polish_existing', 'standard'), ('polish_existing', 'deep'),
            ('plan_from_scratch', 'standard'),
        ]
        sessions = [start_intake(self.proposal, task_mode=task, quality_level=quality) for task, quality in combinations]
        self.assertEqual(len(sessions), 10)
        self.assertTrue(all(item.knowledge_snapshot for item in sessions))
        self.assertTrue(all(item.mode in ('discovery', 'refinement', 'skip', 'evidence_confirmation') for item in sessions))

    def test_routing_uses_rule_and_evidence_readiness(self):
        self.assertEqual(intake_route(
            task_mode='plan_from_scratch', quality_level='quick', rule_readiness='missing_blocking',
            content_maturity='none', evidence_readiness='none',
        ), 'evidence_confirmation')

    def test_phase30_intake_fixture_contract(self):
        fixture = Path(__file__).resolve().parents[3] / 'data' / 'phase30_public_amr_eval' / '07_intake_and_review_workflow.json'
        cases = [item for item in json.loads(fixture.read_text(encoding='utf-8'))['cases'] if item['case_id'].startswith('intake:')]
        self.assertEqual(len(cases), 36)
        for case in cases:
            org = Organization.objects.create(name=case['case_id'], admin=self.proposal.author)
            proposal = Proposal.objects.create(author=self.proposal.author, org=org, content={})
            lengths = {'rough_notes': 100, 'outline': 1000, 'partial_draft': 4000, 'full_draft': 9000}
            if case['content_maturity'] in lengths:
                ProposalSection.objects.create(proposal=proposal, key='fixture', title='fixture', draft_content='x' * lengths[case['content_maturity']])
            inputs = {
                'verified_pack': {'pack_version_id': self.verified_version.id},
                'uploaded_pending': {'pack_version_id': 999999},
                'generic_fallback': {'generic_pack_version_id': self.generic_version.id},
                'missing_blocking': {},
            }[case['rule_readiness']]
            if case['evidence_readiness'] != 'none':
                resource = create_resource_with_chunks(
                    type_='team_profile', title=case['case_id'], source_url='', full_text='fixture evidence',
                    organization_id=str(org.id), knowledge_domain='user_evidence',
                )
                evidence = UserEvidence.objects.create(resource=resource, chunk=resource.chunks.get(), organization_id=str(org.id), proposal=proposal)
                if case['evidence_readiness'] in ('sufficient', 'verified'):
                    EvidenceFact.objects.create(
                        user_evidence=evidence, subject='fixture', predicate='supports', object='case', fact_type='fixture',
                        verification_status='user_confirmed' if case['evidence_readiness'] == 'verified' else 'extracted',
                    )
            detected = detect_profile(proposal, task_mode=case['task_mode'], quality_level=case['quality_level'], inputs=inputs)
            self.assertEqual(detected['rule_readiness'], case['rule_readiness'], case['case_id'])
            self.assertEqual(detected['content_maturity'], case['content_maturity'], case['case_id'])
            self.assertEqual(detected['evidence_readiness'], case['evidence_readiness'], case['case_id'])
            profile = SimpleNamespace(task_mode=case['task_mode'], quality_level=case['quality_level'], **detected)
            policy = build_policy(profile)
            self.assertEqual(policy['grill_mode'], case['expected_grill_mode'], case['case_id'])
            self.assertEqual(policy['question_budget'], case['expected_max_questions'], case['case_id'])
        self.assertEqual(intake_route(
            task_mode='polish_existing', quality_level='quick', rule_readiness='uploaded_pending',
            content_maturity='full_draft', evidence_readiness='sufficient',
        ), 'review')
        self.assertEqual(intake_route(
            task_mode='polish_existing', quality_level='standard', rule_readiness='verified_pack',
            content_maturity='full_draft', evidence_readiness='partial',
        ), 'evidence_confirmation')

    def test_phase40_p03_evaluation_reports_each_fixture_case(self):
        fixture = Path(__file__).resolve().parents[3] / 'data' / 'phase30_public_amr_eval' / '07_intake_and_review_workflow.json'
        cases = [item for item in json.loads(fixture.read_text(encoding='utf-8'))['cases'] if item['case_id'].startswith('intake:')]
        report = evaluate_intake_contract(cases)
        self.assertEqual(report['routing_accuracy'], 1.0)
        self.assertEqual(report['question_budget_accuracy'], 1.0)
        self.assertEqual(report['remaining_discrepancy_count'], 0)
        self.assertEqual(len(report['diagnostics']), 36)
