from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from ai.ingestion import create_resource_with_chunks
from ai.models import Claim, EvidenceFact, GrantPack, GrantPackVersion, GrantProgram, GrantRequirement, UserEvidence
from orgs.models import Organization
from proposals.models import Proposal


class Phase12HumanInterfaceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='phase12-user', password='p')
        self.org = Organization.objects.create(name='Phase12 Org', admin=self.user)
        self.proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.headers = {'HTTP_X_ORG_ID': str(self.org.id)}
        program = GrantProgram.objects.create(name='Phase12 Fund', program_type='youth', authority='Test')
        pack = GrantPack.objects.create(program=program, code='phase12-fund', name='Phase12 Fund')
        self.version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='validated')
        rule_resource = create_resource_with_chunks(type_='guide', title='Guide', source_url='', full_text='Method required.', knowledge_domain='grant_rule')
        self.requirement = GrantRequirement.objects.create(pack_version=self.version, source_chunk=rule_resource.chunks.get(), requirement_type='content', mandatory=True, text='Describe method.')
        evidence_resource = create_resource_with_chunks(type_='profile', title='Profile', source_url='', full_text='Completed project.', organization_id=str(self.org.id), knowledge_domain='user_evidence')
        self.evidence = UserEvidence.objects.create(resource=evidence_resource, chunk=evidence_resource.chunks.get(), organization_id=str(self.org.id))
        self.fact = EvidenceFact.objects.create(user_evidence=self.evidence, subject='Applicant', predicate='completed', object='project', fact_type='project')

    def test_pack_review_and_evidence_confirmation_are_scoped_and_persisted(self):
        response = self.client.get(f'/api/ai/grant-packs/{self.version.id}/review', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['requirements'][0]['id'], self.requirement.id)
        response = self.client.post(
            f'/api/ai/proposals/{self.proposal.id}/evidence-review',
            {'action': 'verify_fact', 'fact_id': self.fact.id, 'verification_status': 'user_confirmed', 'user_role': 'lead'},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.fact.refresh_from_db()
        self.assertEqual(self.fact.verification_status, 'user_confirmed')
        self.assertEqual(self.fact.user_role, 'lead')

    def test_claim_lock_and_evidence_replacement_require_current_proposal_scope(self):
        claim = Claim.objects.create(proposal=self.proposal, text='A claim', claim_type='factual', status='missing_evidence')
        response = self.client.post(
            f'/api/ai/proposals/{self.proposal.id}/claim-decision',
            {'action': 'replace_evidence', 'claim_id': claim.id, 'user_evidence_id': self.evidence.id},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'human_approved')
        response = self.client.post(
            f'/api/ai/proposals/{self.proposal.id}/claim-decision',
            {'action': 'lock', 'claim_id': claim.id},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'locked')

    def test_custom_rule_pack_draft_binds_only_local_rule_resources(self):
        resource = create_resource_with_chunks(
            type_='guideline', title='Custom guide', source_url='', full_text='Must provide a plan.',
            organization_id=str(self.org.id), knowledge_domain='grant_rule',
        )
        response = self.client.post(
            f'/api/ai/proposals/{self.proposal.id}/rule-pack-drafts',
            {'name': 'Custom Fund', 'year': 2026, 'resource_ids': [resource.id]}, format='json', **self.headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'draft')
