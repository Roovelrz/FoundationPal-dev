from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from ai.embedding_service import embed_texts
from ai.models import AIChunk, AIResource, EvidenceUsage
from ai.writer_evidence import parse_writer_result
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


@override_settings(AI_PROVIDER='stub', AI_ASYNC=False)
class WriterEvidenceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='evidence-writer', password='p')
        self.org = Organization.objects.create(name='evidence-org', admin=self.user)
        self.proposal = Proposal.objects.create(author=self.user, org=self.org, content={})
        self.section = ProposalSection.objects.create(proposal=self.proposal, key='intro')
        resource = AIResource.objects.create(
            organization_id=str(self.org.id),
            proposal_id=self.proposal.id,
            source_type='guideline',
            evidence_purpose='constraint',
            display_name='Guideline',
            sha256='a' * 64,
        )
        text = '申请人应当具有高级专业技术职务或者博士学位。'
        AIChunk.objects.create(
            resource=resource,
            stable_chunk_id='chunk-evidence',
            chunk_index=0,
            text=text,
            embedding=embed_texts([text])[0],
            embedding_dimension=len(embed_texts([text])[0]),
        )
        self.client.force_login(self.user)

    def test_write_persists_evidence_and_exposes_section_api(self):
        response = self.client.post(
            '/api/ai/write',
            data={'proposal_id': self.proposal.id, 'section_id': self.section.key, 'answers': {'资格': '申请人资格'}},
            content_type='application/json',
            HTTP_X_ORG_ID=str(self.org.id),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EvidenceUsage.objects.filter(proposal_section=self.section, used_in_prompt=True).count(), 1)
        evidence_response = self.client.get(f'/api/ai/sections/{self.section.id}/evidence', HTTP_X_ORG_ID=str(self.org.id))
        self.assertEqual(evidence_response.status_code, 200)
        self.assertEqual(len(evidence_response.json()['evidence']), 1)
        self.assertEqual(evidence_response.json()['evidence'][0]['section_title'], '文本片段 1')

    def test_write_marks_missing_evidence_when_retrieval_is_empty(self):
        AIChunk.objects.all().delete()
        response = self.client.post(
            '/api/ai/write',
            data={'proposal_id': self.proposal.id, 'section_id': self.section.key, 'answers': {'资格': '申请人资格'}},
            content_type='application/json',
            HTTP_X_ORG_ID=str(self.org.id),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['evidence_ids'], [])
        self.assertEqual(response.json()['missing_evidence'], ['no_retrieved_evidence'])

    def test_writer_result_keeps_draft_when_model_returns_an_unknown_citation(self):
        parsed = parse_writer_result(
            'intro',
            '{"schema_version":"1.0","section_key":"other","draft_markdown":"可保存的草稿。","evidence_ids":["12",999],"warnings":"模型提示","missing_evidence":[]}',
            [12],
        )

        self.assertEqual(parsed['schema_version'], 'v1')
        self.assertEqual(parsed['section_key'], 'intro')
        self.assertEqual(parsed['evidence_ids'], [12])
        self.assertIn('unrecognized_evidence_ids_removed', parsed['warnings'])
