import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from ai.intake import start_intake
from ai.phase40_p03 import evaluate_intake_contract
from ai.models import (
    Claim, ClaimEvidenceBinding, ClaimPlan, Phase11SeedMap, ProposalBrief,
    SectionPlan,
)
from ai.reviewing import IMPLEMENTED_REVIEW_CODES, answer_review_grill, reverify_review_grill, run_review, start_review_grill
from proposals.models import Proposal, ProposalSection


STATUS_MAP = {
    'supported': 'verified', 'missing_evidence': 'missing_evidence',
    'conflicted': 'conflicted', 'locked': 'locked',
}
CLAIM_TYPES = {item[0] for item in Claim.CLAIM_TYPE_CHOICES}


class Command(BaseCommand):
    help = 'Import verified Phase 11 workflow fixtures and execute Intake, Reviewer and Review Grill.'

    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--user-id', required=True, type=int)
        parser.add_argument('--output', default='reports/phase11-claim-workflow.json')
        parser.add_argument('--mapping-kind-prefix', default='')

    def _maps(self, prefix=''):
        rows = Phase11SeedMap.objects.filter(kind__startswith=prefix) if prefix else Phase11SeedMap.objects.all()
        return {(item.kind.removeprefix(prefix), item.external_id): item.target_id for item in rows}

    def _confirmed_section_plan(self, proposal, section, requirement_id):
        version_id = section.proposal.claims.filter(
            addressed_requirements=requirement_id
        ).values_list('addressed_requirements__pack_version_id', flat=True).first()
        if version_id is None:
            from ai.models import GrantRequirement
            version_id = GrantRequirement.objects.get(pk=requirement_id).pack_version_id
        session = start_intake(
            proposal, task_mode='plan_from_scratch', quality_level='standard',
            inputs={'pack_version_id': version_id},
        )
        brief, _ = ProposalBrief.objects.get_or_create(
            proposal=proposal, session=session,
            defaults={'content': {'phase11_eval_fixture': True}, 'confirmed': True},
        )
        if not brief.confirmed:
            brief.confirmed = True
            brief.save(update_fields=['confirmed', 'updated_at'])
        plan = ClaimPlan.objects.create(
            proposal=proposal, brief=brief, policy=session.policy,
            pack_version_id=version_id, planning_mode='create', status='confirmed',
        )
        plan_section = SectionPlan.objects.create(
            claim_plan=plan, section_key=section.key, title=section.title,
        )
        plan_section.target_requirements.add(requirement_id)
        return plan_section

    def handle(self, *args, **options):
        root = Path(options['input_dir'])
        maps = self._maps(options['mapping_kind_prefix'])
        claim_rows = json.loads((root / '06_claim_grounding.json').read_text(encoding='utf-8'))['cases']
        workflow_rows = json.loads((root / '07_intake_and_review_workflow.json').read_text(encoding='utf-8'))['cases']
        claims_by_external_id = {}
        reviewed_sections = {}
        reviewer_issue_codes = set()

        for row in claim_rows:
            proposal_id = maps.get(('proposal', row['proposal_id']))
            requirement_ids = [maps[('grant_requirement', value)] for value in row['requirement_ids'] if ('grant_requirement', value) in maps]
            if not proposal_id or not requirement_ids:
                continue
            proposal = Proposal.objects.get(pk=proposal_id)
            section, _ = ProposalSection.objects.get_or_create(
                proposal=proposal, key=row['section_key'], defaults={'title': row['section_key']},
            )
            claim, _ = Claim.objects.get_or_create(
                proposal=proposal, proposal_section=section, text=row['claim_text'],
                defaults={
                    'claim_type': row['claim_type'] if row['claim_type'] in CLAIM_TYPES else 'interpretive',
                    'status': STATUS_MAP.get(row['expected_status'], 'planned'),
                    'source_mode': 'phase11_eval_fixture',
                },
            )
            claim.addressed_requirements.set(requirement_ids)
            for external_id in row['user_evidence_ids']:
                evidence_id = maps.get(('user_evidence', external_id))
                if evidence_id:
                    ClaimEvidenceBinding.objects.get_or_create(
                        claim=claim, user_evidence_id=evidence_id,
                        defaults={'support_type': 'factual_support', 'support_strength': 'direct', 'reviewer_status': 'accepted'},
                    )
            self._confirmed_section_plan(proposal, section, requirement_ids[0])
            issues = run_review(section)
            reviewed_sections[(proposal.id, section.key)] = (section, issues)
            reviewer_issue_codes.update(issue.code for issue in issues)
            claims_by_external_id[row['claim_external_id']] = claim

        expected_issue_codes = {row['review_issue_code'] for row in workflow_rows if row['case_id'].startswith('review_grill:')}
        review_rows = [row for row in workflow_rows if row['case_id'].startswith('review_grill:')]
        grill_sessions = 0
        grill_answered = 0
        grill_reverified = 0
        review_rows_with_actual_issue = 0
        for row in review_rows:
            proposal_id = maps.get(('proposal', row['proposal_id']))
            key = (proposal_id, row['section_key'])
            section_and_issues = reviewed_sections.get(key)
            if not section_and_issues:
                continue
            section, issues = section_and_issues
            if not issues:
                continue
            review_rows_with_actual_issue += 1
            session = start_review_grill(section)
            grill_sessions += 1
            issue = next((item for item in issues if item.code == row['review_issue_code']), None)
            node = session.nodes.filter(node_id=f'review-{issue.id}').first() if issue else None
            if node:
                answer_review_grill(
                    session, node_id=node.node_id, action='custom', answer='phase11 fixture review decision',
                    idempotency_key=f'phase11-review-{row["case_id"]}', user=None,
                )
                grill_answered += 1
                grill_reverified += reverify_review_grill(session, issue_id=issue.id)

        user = get_user_model().objects.get(pk=options['user_id'])
        intake_rows = [row for row in workflow_rows if row['case_id'].startswith('intake:')]
        intake_contract = evaluate_intake_contract(intake_rows)

        payload = {
            'claim_case_count': len(claim_rows),
            'reviewer_execution': {
                'reviewed_section_count': len(reviewed_sections),
                'actual_issue_codes': sorted(reviewer_issue_codes),
                'expected_review_grill_issue_codes_implemented': sorted(expected_issue_codes & IMPLEMENTED_REVIEW_CODES),
                'expected_review_grill_issue_codes_observed': sorted(expected_issue_codes & reviewer_issue_codes),
                'expected_review_grill_issue_codes_not_implemented': sorted(expected_issue_codes - IMPLEMENTED_REVIEW_CODES),
                'expected_review_grill_issue_codes_not_observed': sorted(expected_issue_codes - reviewer_issue_codes),
            },
            'review_grill_execution': {
                'fixture_case_count': len(review_rows),
                'cases_with_actual_reviewer_issues': review_rows_with_actual_issue,
                'sessions_created': grill_sessions,
                'first_decisions_recorded': grill_answered,
                'reverification_successes': grill_reverified,
                'direct_closures': 0,
            },
            'intake_execution': {
                **intake_contract,
            },
        }
        output = Path(options['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('phase11_claim_workflow_eval_complete'))
