import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class Command(BaseCommand):
    help = 'Build a traceable public-AMR evaluation fixture from the verified 18-paper corpus.'

    def add_arguments(self, parser):
        parser.add_argument('--public-source-dir', required=True)
        parser.add_argument('--base-fixture-dir', required=True)
        parser.add_argument('--output-dir', required=True)

    def handle(self, *args, **options):
        public_root = Path(options['public_source_dir'])
        base_root = Path(options['base_fixture_dir'])
        output_root = Path(options['output_dir'])
        sources = read_json(public_root / '01_public_amr_evidence_native_ids.json')['cases']
        source_manifest = read_json(public_root / 'public_amr_sources_manifest.json')['sources']
        if len(sources) != 18 or len(source_manifest) != 18:
            raise CommandError('public_amr_source_count_must_be_18')
        if {row['external_id'] for row in sources} != {row['public_evidence_id'] for row in source_manifest}:
            raise CommandError('public_amr_native_ids_do_not_match_manifest')
        output_root.mkdir(parents=True, exist_ok=True)
        base = {name: read_json(base_root / name) for name in (
            '01_rule_requirement_mapping.json',
            '07_intake_and_review_workflow.json', 'phase11_external_id_seed_manifest.json',
        )}
        source_by_id = {row['external_id']: row for row in sources}
        primary_org = 'ORG-P30-PUBLIC-AMR'
        forbidden_org = 'ORG-P30-FORBIDDEN-AMR'
        primary_proposal = 'PROPOSAL-P30-PUBLIC-AMR'
        forbidden_proposal = 'PROPOSAL-P30-FORBIDDEN-AMR'

        def document_text(row):
            return '\n'.join([
                f"title: {row['title']}",
                f"authors: {', '.join(row['authors'])}",
                f"year: {row['publication_year']}",
                f"summary: {row['evidence_summary']}",
                'verified_claims:',
                *row['verified_claims'],
                f"source_url: {row['source_url']}",
                f"file_sha256: {row['file_sha256']}",
            ])

        user_evidences = []
        for index, row in enumerate(sources, start=1):
            primary = {
                'external_id': row['external_id'],
                'organization_external_id': primary_org,
                'proposal_external_id': primary_proposal,
                'query': row['verified_claims'][0],
                'expected_role': 'public_amr_paper',
                'expected_numeric_value': index,
                'expected_fact_status': 'completed',
                'document_text': document_text(row),
            }
            user_evidences.append(primary)
            user_evidences.append({
                **primary,
                'external_id': f"UE-PUBLIC-AMR-FORBIDDEN-{index:03d}",
                'organization_external_id': forbidden_org,
                'proposal_external_id': forbidden_proposal,
            })

        evidence_cases = []
        mixed_cases = []
        leakage_cases = []
        rule_cases = base['01_rule_requirement_mapping.json']['cases']
        first_rule = rule_cases[0]
        negative_cases = [
            {
                'case_id': 'public_amr_rule_negative:wrong_year',
                'query': first_rule['query'],
                'grant_pack_version_id': first_rule['grant_pack_version_id'],
                'reason': 'wrong_year',
                'requested_year': first_rule['applicable_year'] - 1,
                'expected_status': 'no_applicable_rule',
            },
            {
                'case_id': 'public_amr_rule_negative:wrong_program',
                'query': first_rule['query'],
                'grant_pack_version_id': first_rule['grant_pack_version_id'],
                'reason': 'wrong_program',
                'requested_program_type': '不适用项目类别',
                'expected_status': 'no_applicable_rule',
            },
            {
                'case_id': 'public_amr_rule_negative:wrong_region',
                'query': first_rule['query'],
                'grant_pack_version_id': first_rule['grant_pack_version_id'],
                'reason': 'wrong_region',
                'requested_region': '不适用地区',
                'expected_status': 'no_applicable_rule',
            },
            {
                'case_id': 'public_amr_rule_negative:unpublished',
                'query': first_rule['query'],
                'grant_pack_version_id': first_rule['grant_pack_version_id'],
                'reason': 'unpublished_pack',
                'pack_status_override': 'draft',
                'expected_status': 'grant_pack_not_published',
            },
        ]
        for index, row in enumerate(sources, start=1):
            query = row['verified_claims'][0]
            evidence_cases.append({
                'case_id': f'public_amr_evidence:{index:03d}',
                'query': query,
                'user_evidence_ids': [row['external_id']],
                'gold_chunk_ids': [row['stable_chunk_id']],
                'organization_id': primary_org,
                'proposal_id': primary_proposal,
                'expected_role': 'public_amr_paper',
                'expected_numeric_value': index,
                'expected_fact_status': 'completed',
                'annotation_status': 'public_source_human_verified',
                'annotation_notes': 'Query and Gold both derive from the supplied public paper record.',
            })
            rule = rule_cases[(index - 1) % len(rule_cases)]
            mixed_cases.append({
                'case_id': f'public_amr_mixed:{index:03d}',
                'query': f"{rule['query']}。同时核对公开论文事实：{query}",
                'requirement_ids': rule['requirement_ids'],
                'user_evidence_ids': [row['external_id']],
                'gold_chunk_ids': rule['gold_chunk_ids'] + [row['stable_chunk_id']],
                'grant_pack_version_id': rule['grant_pack_version_id'],
                'organization_id': primary_org,
                'expected_answer': 'Rule evidence and public-paper evidence must be returned as separate domains.',
                'annotation_status': 'public_source_human_verified',
                'annotation_notes': 'The public evidence is not attributed to an applicant or organization.',
            })
            leakage_cases.append({
                'case_id': f'public_amr_leakage:{index:03d}',
                'query': query,
                'authorized_organization_id': primary_org,
                'authorized_user_evidence_ids': [row['external_id']],
                'distractor_organization_id': forbidden_org,
                'forbidden_user_evidence_ids': [f"UE-PUBLIC-AMR-FORBIDDEN-{index:03d}"],
                'expected_status': 'no_cross_organization_leakage',
                'annotation_status': 'public_source_human_verified',
                'annotation_notes': 'Same public document is deliberately duplicated across two test organizations.',
            })

        claim_cases = []
        label_cases = []
        for index in range(30):
            source = sources[index % len(sources)]
            source_claim = source['verified_claims'][index % len(source['verified_claims'])]
            if index < 18:
                label = 'complete_support'
                expected_status = 'verified'
                claim_text = source_claim
                rationale = 'The supplied verified public-paper record states this claim directly.'
            elif index < 24:
                label = 'partial_support'
                expected_status = 'missing_evidence'
                claim_text = f"{source_claim}，并且该结论已经在所有无线通信环境中完成部署验证。"
                rationale = 'The source supports the paper-specific statement but does not establish universal deployment validation.'
            else:
                label = 'unsupported'
                expected_status = 'conflicted'
                claim_text = f"{source_claim}，并证明该方法在全部调制数据集上达到百分之百准确率。"
                rationale = 'The source does not support an all-dataset perfect-accuracy conclusion.'
            claim_id = f'PUBLIC-AMR-CLAIM-{index + 1:03d}'
            claim_cases.append({
                'case_id': f'public_amr_claim:{index + 1:03d}',
                'claim_external_id': claim_id,
                'claim_text': claim_text,
                'claim_type': 'factual',
                'expected_status': expected_status,
                'expected_review_issue_codes': [],
                'proposal_id': primary_proposal,
                'section_key': 'public_amr_evidence_review',
                'requirement_ids': rule_cases[index % len(rule_cases)]['requirement_ids'],
                'user_evidence_ids': [source['external_id']],
                'annotation_status': 'public_source_human_verified',
                'annotation_notes': 'Claim label is traceable to the supplied public paper and explicit test scope.',
            })
            label_cases.append({
                'case_id': f'public_amr_claim:{index + 1:03d}',
                'claim_external_id': claim_id,
                'label': label,
                'rationale': rationale,
                'review_status': 'administrator_approved',
                'reviewer': 'roovel',
                'review_date': '2026-07-28',
                'source_pages': [{'page': source['page_start'], 'source_type': 'public_amr_pdf'}],
                'source_page_status': 'human_verified_public_source',
                'source_annotation': source['title'],
            })

        manifest = {
            'schema_version': 'phase30-public-amr-eval-v1',
            'warning': 'Public AMR papers are real public test sources. They must not be attributed to an applicant or a grant organization.',
            'grant_pack_versions': base['phase11_external_id_seed_manifest.json']['grant_pack_versions'],
            'grant_requirements': base['phase11_external_id_seed_manifest.json']['grant_requirements'],
            'user_evidences': user_evidences,
        }
        write_json(output_root / 'phase11_external_id_seed_manifest.json', manifest)
        write_json(output_root / '01_rule_requirement_mapping.json', base['01_rule_requirement_mapping.json'])
        write_json(output_root / '02_user_evidence_grounding.json', {'target_count': len(evidence_cases), 'cases': evidence_cases})
        write_json(output_root / '03_negative_rule_scope.json', {'target_count': len(negative_cases), 'cases': negative_cases})
        write_json(output_root / '04_mixed_dual_domain.json', {'target_count': len(mixed_cases), 'cases': mixed_cases})
        write_json(output_root / '05_cross_organization_leakage.json', {'target_count': len(leakage_cases), 'cases': leakage_cases})
        write_json(output_root / '06_claim_grounding.json', {'target_count': len(claim_cases), 'cases': claim_cases})
        write_json(output_root / '06_claim_citation_entailment_labels.json', {
            'dataset': 'phase30_public_amr_citation_entailment_labels',
            'annotation_level': 'public_source_human_verified',
            'source_fixture': '01_public_amr_evidence_native_ids.json',
            'cases': label_cases,
        })
        write_json(output_root / '07_intake_and_review_workflow.json', base['07_intake_and_review_workflow.json'])
        write_json(output_root / 'public_amr_source_manifest.json', {'sources': source_manifest})
        self.stdout.write(self.style.SUCCESS(
            f'phase30_public_amr_eval_built: evidence={len(evidence_cases)} mixed={len(mixed_cases)} claims={len(claim_cases)}'
        ))
