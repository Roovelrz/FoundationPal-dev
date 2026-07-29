import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from ai.domain_retrieval import EvidenceQuery, RuleQuery
from ai.ingestion import create_resource_with_chunks
from ai.models import EvidenceFact, GrantPack, GrantPackVersion, GrantProgram, GrantRequirement, Phase11SeedMap, UserEvidence
from ai.query_router import retrieve_dual, search_grant_rules, search_user_evidence, split_dual_query


class Phase11RetrievalDiagnosticsTests(TestCase):
    def test_cross_organization_seed_import_uses_fixture_ids_and_is_idempotent(self):
        user = get_user_model().objects.create_user(username='phase11-seed-user')
        source_resource = create_resource_with_chunks(
            type_='team_profile', title='Original source', source_url='', full_text='Original source fact.',
            organization_id='source-org', knowledge_domain='user_evidence',
        )
        source = UserEvidence.objects.create(
            resource=source_resource, chunk=source_resource.chunks.get(), organization_id='source-org',
        )
        Phase11SeedMap.objects.create(
            kind='test_p1_user_evidence', external_id='UE-P0-AUTHORIZED', target_id=source.id,
        )
        payload = {'cases': [{
            'authorized_organization_id': 'ORG-P0-AUTHORIZED',
            'authorized_user_evidence_ids': ['UE-P0-AUTHORIZED'],
            'distractor_organization_id': 'ORG-P0-FORBIDDEN',
            'forbidden_user_evidence_ids': ['UE-P0-FORBIDDEN'],
            'query': 'shared retrieval text',
            'annotation_notes': 'fixture',
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'leakage.json'
            bindings_path = Path(directory) / 'bindings.json'
            path.write_text(json.dumps(payload), encoding='utf-8')
            bindings_path.write_text(json.dumps({'cases': [{
                'external_id': 'UE-P0-FORBIDDEN', 'source_user_evidence_id': 'UE-P0-AUTHORIZED',
            }]}), encoding='utf-8')
            for _ in range(2):
                call_command(
                    'import_phase11_cross_org_seeds', input_file=path, user_id=user.id,
                    source_binding_file=bindings_path, mapping_kind_prefix='test_p1_',
                )

        mappings = Phase11SeedMap.objects.filter(kind__startswith='test_p1_')
        self.assertEqual(mappings.filter(kind='test_p1_organization').count(), 2)
        self.assertEqual(mappings.filter(kind='test_p1_user_evidence').count(), 2)
        self.assertEqual(UserEvidence.objects.count(), 2)
        forbidden_id = mappings.get(external_id='UE-P0-FORBIDDEN').target_id
        self.assertEqual(UserEvidence.objects.get(pk=forbidden_id).chunk.text, source.chunk.text)

    def test_split_dual_query_keeps_rule_and_evidence_clauses_separate(self):
        rule_text, evidence_text = split_dual_query(
            '请核对申请资格和经费限制。团队论文是否能支持这项申请。'
        )

        self.assertEqual(rule_text, '请核对申请资格和经费限制')
        self.assertEqual(evidence_text, '团队论文是否能支持这项申请')

    def test_split_dual_query_keeps_ambiguous_question_available_to_both_domains(self):
        rule_text, evidence_text = split_dual_query('请判断是否适合申报')

        self.assertEqual(rule_text, '请判断是否适合申报')
        self.assertEqual(evidence_text, '请判断是否适合申报')

    def test_rule_search_exposes_candidate_and_filter_diagnostics(self):
        program = GrantProgram.objects.create(name='Eval Fund', program_type='youth', region='CN', authority='Eval')
        pack = GrantPack.objects.create(program=program, code='eval-fund', name='Eval Fund')
        version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='published')
        resource = create_resource_with_chunks(
            type_='guideline', title='Rule', source_url='', full_text='Applicants must submit a budget.',
            knowledge_domain='grant_rule',
        )
        resource.grant_pack = pack
        resource.classification_status = 'classified'
        resource.save(update_fields=['grant_pack', 'classification_status'])
        requirement = GrantRequirement.objects.create(
            pack_version=version, source_chunk=resource.chunks.get(), requirement_type='budget', mandatory=True,
            text='Applicants must submit a budget.', source_excerpt='Applicants must submit a budget.',
        )

        result = search_grant_rules(RuleQuery(pack_version_id=version.id, user_question='budget'))

        self.assertEqual(result['results'][0]['requirement_id'], requirement.id)
        self.assertIn(requirement.id, result['audit_candidates'])
        self.assertIn('filter_counts', result)
        self.assertIn('audit_candidate_details', result)
        self.assertIn('source_page_start', result['results'][0]['atomic_rule'])
        self.assertEqual(
            set(result['results'][0]['ranking_factors']),
            {'rrf', 'lexical_overlap', 'number_match', 'section_match', 'title_match', 'applicability_match', 'source_traceability'},
        )

    def test_evidence_search_exposes_scope_diagnostics(self):
        resource = create_resource_with_chunks(
            type_='team_profile', title='Evidence', source_url='', full_text='Team completed experiment.',
            organization_id='phase11-org', knowledge_domain='user_evidence',
        )
        evidence = UserEvidence.objects.create(resource=resource, chunk=resource.chunks.get(), organization_id='phase11-org')

        result = search_user_evidence(EvidenceQuery(organization_id='phase11-org', user_question='experiment'))

        self.assertEqual(result['results'][0]['user_evidence_id'], evidence.id)
        self.assertEqual(result['filter_counts']['organization_scope'], 1)
        self.assertIn('proposal_id', result['applied_filters'])

    def test_evidence_search_filters_time_and_prefers_confirmed_fact(self):
        resource = create_resource_with_chunks(
            type_='team_profile', title='Evidence one', source_url='', full_text='Team completed experiment in 2025.',
            organization_id='phase11-org', knowledge_domain='user_evidence',
        )
        confirmed = UserEvidence.objects.create(resource=resource, chunk=resource.chunks.get(), organization_id='phase11-org')
        EvidenceFact.objects.create(
            user_evidence=confirmed, subject='team', predicate='completed', object='experiment', fact_type='experiment',
            time_range={'year': '2025'}, verification_status='user_confirmed',
        )
        old_resource = create_resource_with_chunks(
            type_='team_profile', title='Evidence two', source_url='', full_text='Team completed experiment in 2022.',
            organization_id='phase11-org', knowledge_domain='user_evidence',
        )
        old = UserEvidence.objects.create(resource=old_resource, chunk=old_resource.chunks.get(), organization_id='phase11-org')
        EvidenceFact.objects.create(
            user_evidence=old, subject='team', predicate='completed', object='experiment', fact_type='experiment',
            time_range={'year': '2022'}, verification_status='extracted',
        )

        result = search_user_evidence(EvidenceQuery(
            organization_id='phase11-org', claim_intent='completed experiment', time_range={'year': '2025'}, user_question='experiment',
        ))

        self.assertEqual([row['user_evidence_id'] for row in result['results']], [confirmed.id])
        self.assertEqual(result['filter_counts']['after_time_range'], 1)
        self.assertEqual(result['results'][0]['ranking_factors']['verified_fact_count'], 1)

    def test_rejected_only_evidence_is_not_a_candidate(self):
        resource = create_resource_with_chunks(
            type_='team_profile', title='Synthetic fixture', source_url='', full_text='Synthetic evidence only.',
            organization_id='phase11-org', knowledge_domain='user_evidence',
        )
        evidence = UserEvidence.objects.create(resource=resource, chunk=resource.chunks.get(), organization_id='phase11-org')
        EvidenceFact.objects.create(
            user_evidence=evidence, subject='fixture', predicate='is', object='synthetic', fact_type='test', verification_status='rejected',
        )

        result = search_user_evidence(EvidenceQuery(organization_id='phase11-org', user_question='synthetic'))

        self.assertEqual(result['results'], [])

    def test_dual_retrieval_runs_both_queries_and_uses_domain_budget(self):
        program = GrantProgram.objects.create(name='Eval Fund', program_type='youth', region='CN', authority='Eval')
        pack = GrantPack.objects.create(program=program, code='eval-fund', name='Eval Fund')
        version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='published')
        rule_resource = create_resource_with_chunks(
            type_='guideline', title='Rule', source_url='', full_text='Applicants must submit a budget.', knowledge_domain='grant_rule',
        )
        GrantRequirement.objects.create(
            pack_version=version, source_chunk=rule_resource.chunks.get(), requirement_type='budget', mandatory=True, text='Applicants must submit a budget.',
        )
        evidence_resource = create_resource_with_chunks(
            type_='team_profile', title='Evidence', source_url='', full_text='Team completed an experiment.',
            organization_id='phase11-org', knowledge_domain='user_evidence',
        )
        UserEvidence.objects.create(resource=evidence_resource, chunk=evidence_resource.chunks.get(), organization_id='phase11-org')

        result = retrieve_dual(
            question='请核对规则',
            rule_query=RuleQuery(pack_version_id=version.id, user_question='budget'),
            evidence_query=EvidenceQuery(organization_id='phase11-org', user_question='experiment'),
        )

        self.assertEqual(result.intent['required_domains'], ['grant_rule', 'user_evidence'])
        self.assertEqual(result.rule_results['status'], 'ok')
        self.assertEqual(result.user_evidence_results['status'], 'ok')
        self.assertLessEqual(len(result.context_budget['rule_context_ids']), 3)
        self.assertLessEqual(len(result.context_budget['evidence_context_ids']), 3)

    def test_rule_applicability_returns_insufficient_information_for_missing_required_fact(self):
        program = GrantProgram.objects.create(name='Eval Fund', program_type='youth', region='CN', authority='Eval')
        pack = GrantPack.objects.create(program=program, code='scope-fund', name='Scope Fund')
        version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='published')
        resource = create_resource_with_chunks(type_='guideline', title='Rule', source_url='', full_text='Joint applications need an agreement.', knowledge_domain='grant_rule')
        GrantRequirement.objects.create(
            pack_version=version, source_chunk=resource.chunks.get(), requirement_type='content', mandatory=True,
            text='Joint applications need an agreement.', applicability={'joint_application': True, 'source_id': 'display-only'},
        )

        result = search_grant_rules(RuleQuery(pack_version_id=version.id, user_question='agreement'))

        self.assertEqual(result['status'], 'insufficient_information')
        self.assertEqual(result['missing_application_facts'], ['joint_application'])
        self.assertEqual(result['results'][0]['applicability_status'], 'insufficient_information')

    def test_rule_applicability_filters_non_applicable_structured_fact(self):
        program = GrantProgram.objects.create(name='Eval Fund', program_type='youth', region='CN', authority='Eval')
        pack = GrantPack.objects.create(program=program, code='category-fund', name='Category Fund')
        version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='published')
        resource = create_resource_with_chunks(type_='guideline', title='Rule', source_url='', full_text='Youth A rule.', knowledge_domain='grant_rule')
        GrantRequirement.objects.create(
            pack_version=version, source_chunk=resource.chunks.get(), requirement_type='content', mandatory=True,
            text='Youth A rule.', applicability={'program_category': 'youth_a'},
        )

        result = search_grant_rules(RuleQuery(pack_version_id=version.id, program_category='youth_b', user_question='rule'))

        self.assertEqual(result['status'], 'no_applicable_rule')

    def test_explicit_scope_conflict_overrides_other_missing_scope_facts(self):
        program = GrantProgram.objects.create(name='Eval Fund', program_type='youth', region='CN', authority='Eval')
        pack = GrantPack.objects.create(program=program, code='priority-scope-fund', name='Priority scope fund')
        version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='published')
        resource = create_resource_with_chunks(type_='guideline', title='Rule', source_url='', full_text='Youth A rule.', knowledge_domain='grant_rule')
        GrantRequirement.objects.create(
            pack_version=version, source_chunk=resource.chunks.get(), requirement_type='content', mandatory=True,
            text='Youth A rule.', applicability={'program_category': 'youth_a', 'year': 2026},
        )

        result = search_grant_rules(RuleQuery(pack_version_id=version.id, year=2025, user_question='rule'))

        self.assertEqual(result['status'], 'no_applicable_rule')

    def test_requirement_applicability_overrides_pack_level_program_metadata(self):
        program = GrantProgram.objects.create(name='Pack default', program_type='general', region='CN', authority='Eval')
        pack = GrantPack.objects.create(program=program, code='mixed-program-pack', name='Mixed program pack')
        version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='published')
        resource = create_resource_with_chunks(type_='guideline', title='Youth rule', source_url='', full_text='Youth applicants need an appendix.', knowledge_domain='grant_rule')
        requirement = GrantRequirement.objects.create(
            pack_version=version, source_chunk=resource.chunks.get(), requirement_type='content', mandatory=True,
            text='Youth applicants need an appendix.', applicability={'program_type': 'youth', 'year': 2026, 'region': 'CN'},
        )

        result = search_grant_rules(RuleQuery(
            pack_version_id=version.id, program_type='youth', year=2026, region='CN', user_question='appendix',
        ))

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['results'][0]['requirement_id'], requirement.id)

    def test_rule_search_rejects_numeric_only_atomic_rule(self):
        program = GrantProgram.objects.create(name='Eval Fund', program_type='youth', region='CN', authority='Eval')
        pack = GrantPack.objects.create(program=program, code='atomic-fund', name='Atomic Fund')
        version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1', status='published')
        resource = create_resource_with_chunks(type_='guideline', title='Rule', source_url='', full_text='1234', knowledge_domain='grant_rule')
        GrantRequirement.objects.create(pack_version=version, source_chunk=resource.chunks.get(), requirement_type='content', mandatory=True, text='1234')

        result = search_grant_rules(RuleQuery(pack_version_id=version.id, user_question='rule'))

        self.assertEqual(result['status'], 'no_applicable_rule')
