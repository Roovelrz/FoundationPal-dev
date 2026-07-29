from django.contrib.auth import get_user_model
from django.test import TestCase

from ai.claim_planning import confirm_claim_plan, create_claim_plan
from ai.ingestion import create_resource_with_chunks
from ai.intake import start_intake
from ai.models import (
    Claim, ClaimEvidenceBinding, ClaimSentenceMapping, EvidenceFact, GrantPack, GrantPackVersion, GrantProgram, GrantRequirement,
    GrillDecisionNode, ProposalBrief, ProposalDecision, ReviewDecision, ReviewRevision, UserEvidence,
)
from ai.reviewing import answer_review_grill, apply_local_revision, prepare_writer_run, reverify_review_grill, run_review, start_review_grill
from orgs.models import Organization
from proposals.models import Proposal


class Phase9ReviewTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='phase9-user', password='p')
        self.user = user
        self.org = Organization.objects.create(name='Phase9 Org', admin=user)
        self.proposal = Proposal.objects.create(author=user, org=self.org, content={})
        program = GrantProgram.objects.create(name='Review Fund', program_type='youth', authority='Review')
        pack = GrantPack.objects.create(program=program, code='review-fund', name='Review Fund')
        self.version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='published')
        resource = create_resource_with_chunks(type_='guideline', title='Guide', source_url='', full_text='Mandatory requirement.', knowledge_domain='grant_rule')
        GrantRequirement.objects.create(pack_version=self.version, source_chunk=resource.chunks.get(), requirement_type='content', mandatory=True, text='Describe method.', source_excerpt='Describe method.')
        session = start_intake(self.proposal, task_mode='plan_from_scratch', quality_level='deep', inputs={'pack_version_id': self.version.id})
        node = GrillDecisionNode.objects.create(session=session, node_id='method', topic='methodology', question='Method', question_type='planning_decision', priority=99)
        ProposalDecision.objects.create(proposal=self.proposal, session=session, node=node, topic='methodology', value='Protected method')
        ProposalBrief.objects.create(proposal=self.proposal, session=session, content={'methodology': 'Protected method'}, confirmed=True)
        self.plan = create_claim_plan(self.proposal, pack_version_id=self.version.id)
        confirm_claim_plan(self.plan)
        self.section = self.proposal.sections.get()

    def test_writer_context_selects_mode_and_maps_claim_sentence(self):
        run, _, _ = prepare_writer_run(self.section)
        self.assertEqual(run.writing_mode, 'generate')
        claim = Claim.objects.get(proposal_section=self.section)
        apply_local_revision(self.section, revised_text=f'Introduction. {claim.text} End.', user_id=self.user.id)
        mapping = ClaimSentenceMapping.objects.get(claim=claim)
        self.assertEqual(mapping.text_snapshot, claim.text)

    def test_fact_issue_enters_review_grill_and_creates_review_decision(self):
        claim = Claim.objects.get(proposal_section=self.section)
        claim.claim_type = 'factual'
        claim.status = 'missing_evidence'
        claim.save(update_fields=['claim_type', 'status'])
        issues = run_review(self.section)
        self.assertTrue(any(item.code == 'missing_claim_evidence' for item in issues))
        session = start_review_grill(self.section)
        node = session.nodes.get()
        answer_review_grill(session, node_id=node.node_id, action='custom', answer='补充团队证明材料', idempotency_key='review-one', user=self.user)
        self.assertEqual(ReviewDecision.objects.count(), 1)

    def test_local_revision_preserves_locked_claim_and_audits_diff(self):
        claim = Claim.objects.get(proposal_section=self.section)
        claim.status = 'locked'
        claim.text = 'Locked fact'
        claim.save(update_fields=['status', 'text'])
        self.section.draft_content = 'Locked fact and details'
        self.section.save(update_fields=['draft_content'])
        with self.assertRaisesRegex(ValueError, 'protected_fact_modified'):
            apply_local_revision(self.section, revised_text='Changed details', user_id=self.user.id)
        apply_local_revision(self.section, revised_text='Locked fact and improved details', user_id=self.user.id)
        self.assertEqual(ReviewRevision.objects.count(), 1)

    def test_numerical_conflict_is_ledgered_and_requires_reverification(self):
        resource = create_resource_with_chunks(
            type_='team_profile', title='Metric evidence', source_url='', full_text='The measured value is 6.',
            organization_id=str(self.org.id), knowledge_domain='user_evidence',
        )
        evidence = UserEvidence.objects.create(resource=resource, chunk=resource.chunks.get(), organization_id=str(self.org.id))
        EvidenceFact.objects.create(
            user_evidence=evidence, subject='metric', predicate='value', object='6', fact_type='metric',
            numeric_value='6', verification_status='user_confirmed',
        )
        claim = Claim.objects.create(
            proposal=self.proposal, proposal_section=self.section, text='Measured value is 7.', claim_type='numerical', status='verified',
        )
        ClaimEvidenceBinding.objects.create(claim=claim, user_evidence=evidence, reviewer_status='accepted')

        issues = run_review(self.section)
        issue = next(item for item in issues if item.code == 'numerical_conflict')
        claim.refresh_from_db()
        self.assertEqual(claim.ledger['evidence_numeric_values'], ['6'])
        session = start_review_grill(self.section)
        node = session.nodes.get(node_id=f'review-{issue.id}')
        answer_review_grill(session, node_id=node.node_id, action='custom', answer='correct metric', idempotency_key='numeric-one', user=self.user)
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'needs_user_decision')

        claim.text = 'Measured value is 6.'
        claim.save(update_fields=['text'])
        self.assertTrue(reverify_review_grill(session, issue_id=issue.id))

    def test_deterministic_status_attachment_budget_and_decision_checks(self):
        resource = create_resource_with_chunks(
            type_='team_profile', title='Project evidence', source_url='', full_text='Project is ongoing.',
            organization_id=str(self.org.id), knowledge_domain='user_evidence',
        )
        evidence = UserEvidence.objects.create(resource=resource, chunk=resource.chunks.get(), organization_id=str(self.org.id))
        EvidenceFact.objects.create(
            user_evidence=evidence, subject='project', predicate='status', object='ongoing', fact_type='project',
            fact_status='ongoing', verification_status='user_confirmed',
        )
        completed = Claim.objects.create(
            proposal=self.proposal, proposal_section=self.section, text='项目已经结题。', claim_type='factual', status='verified',
        )
        ClaimEvidenceBinding.objects.create(claim=completed, user_evidence=evidence, reviewer_status='accepted')
        Claim.objects.create(
            proposal=self.proposal, proposal_section=self.section, text='附件材料已经提交。', claim_type='factual', status='verified',
        )
        Claim.objects.create(
            proposal=self.proposal, proposal_section=self.section, text='预算经费为10万元。', claim_type='numerical', status='verified',
        )
        decision = ProposalDecision.objects.get(topic='methodology')
        decision_claim = Claim.objects.create(
            proposal=self.proposal, proposal_section=self.section, text='方法路线已调整。', claim_type='factual', status='verified',
        )
        decision_claim.proposal_decisions.add(decision)

        codes = {item.code for item in run_review(self.section)}

        self.assertTrue({'completion_status_conflict', 'missing_attachment_evidence', 'missing_budget_decision', 'human_decision_preserved'}.issubset(codes), codes)
