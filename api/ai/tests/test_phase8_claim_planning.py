from django.contrib.auth import get_user_model
from django.test import TestCase

from ai.claim_planning import confirm_claim_plan, create_claim_plan, invalidate_for_decision
from ai.ingestion import create_resource_with_chunks
from ai.intake import start_intake
from ai.models import (
    Claim, ClaimEvidenceBinding, GrantPack, GrantPackVersion, GrantProgram, GrantRequirement, GrillDecisionNode,
    ProposalBrief, ProposalDecision, UserEvidence,
)
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


class Phase8ClaimPlanningTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='phase8-user', password='p')
        self.org = Organization.objects.create(name='Phase8 Org', admin=user)
        self.proposal = Proposal.objects.create(author=user, org=self.org, content={})
        program = GrantProgram.objects.create(name='Test Fund', program_type='youth', authority='Test')
        pack = GrantPack.objects.create(program=program, code='test-fund', name='Test Fund')
        self.version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='published')
        resource = create_resource_with_chunks(type_='guideline', title='Guide', source_url='', full_text='Mandatory content.', knowledge_domain='grant_rule')
        self.requirement = GrantRequirement.objects.create(
            pack_version=self.version, source_chunk=resource.chunks.get(), requirement_type='content',
            mandatory=True, text='Describe the proposed work.', source_excerpt='Describe the proposed work.',
        )

    def _confirmed_brief(self, topic='research_goal'):
        session = start_intake(self.proposal, task_mode='plan_from_scratch', quality_level='standard', inputs={'pack_version_id': self.version.id})
        node = GrillDecisionNode.objects.create(session=session, node_id='confirmed-source', topic=topic, question='Confirmed decision', question_type='planning_decision', priority=99)
        decision = ProposalDecision.objects.create(proposal=self.proposal, session=session, node=node, topic=topic, value='Confirmed value')
        brief = ProposalBrief.objects.create(proposal=self.proposal, session=session, content={topic: 'Confirmed value'}, confirmed=True)
        return brief, decision

    def test_confirmed_brief_creates_requirement_covered_claim_plan(self):
        _, decision = self._confirmed_brief()
        plan = create_claim_plan(self.proposal, pack_version_id=self.version.id)
        self.assertEqual(plan.requirement_gaps, [])
        section = plan.section_plans.get()
        self.assertEqual(list(section.target_requirements.values_list('id', flat=True)), [self.requirement.id])
        intent = section.claim_intents_records.get()
        self.assertEqual(intent.proposal_decision_id, decision.id)
        self.assertEqual(intent.claim_type, 'proposed')

    def test_missing_evidence_is_visible_before_claim_materialization(self):
        self._confirmed_brief(topic='existing_foundation')
        plan = create_claim_plan(self.proposal, pack_version_id=self.version.id)
        self.assertEqual(len(plan.evidence_gaps), 1)
        self.assertEqual(Claim.objects.count(), 0)
        confirm_claim_plan(plan)
        self.assertEqual(Claim.objects.get().status, 'missing_evidence')
        self.assertEqual(ClaimEvidenceBinding.objects.filter(claim=Claim.objects.get(), user_evidence__isnull=False).count(), 0)

    def test_factual_claim_binds_available_user_evidence_on_confirmation(self):
        resource = create_resource_with_chunks(type_='team_profile', title='Team', source_url='', full_text='Completed project.', organization_id=str(self.org.id), knowledge_domain='user_evidence')
        UserEvidence.objects.create(resource=resource, chunk=resource.chunks.get(), organization_id=str(self.org.id))
        self._confirmed_brief(topic='existing_foundation')
        plan = create_claim_plan(self.proposal, pack_version_id=self.version.id)
        confirm_claim_plan(plan)
        self.assertEqual(Claim.objects.get().status, 'planned')
        self.assertEqual(ClaimEvidenceBinding.objects.filter(claim=Claim.objects.get(), user_evidence__isnull=False).count(), 1)

    def test_unconfirmed_brief_and_wrong_pack_are_rejected(self):
        session = start_intake(self.proposal, task_mode='plan_from_scratch', quality_level='quick', inputs={'pack_version_id': self.version.id})
        ProposalBrief.objects.create(proposal=self.proposal, session=session, content={}, confirmed=False)
        with self.assertRaisesRegex(ValueError, 'confirmed_proposal_brief_required'):
            create_claim_plan(self.proposal, pack_version_id=self.version.id)
        self._confirmed_brief()
        with self.assertRaisesRegex(ValueError, 'published_grant_pack_required'):
            create_claim_plan(self.proposal, pack_version_id=999)

    def test_decision_change_marks_only_related_plan_and_claim_outdated(self):
        _, decision = self._confirmed_brief()
        plan = create_claim_plan(self.proposal, pack_version_id=self.version.id)
        confirm_claim_plan(plan)
        invalidate_for_decision(decision)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'needs_replan')
        self.assertEqual(Claim.objects.get().status, 'outdated')
        ProposalSection.objects.get(key=plan.section_plans.get().section_key)
