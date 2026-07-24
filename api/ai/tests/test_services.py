from django.contrib.auth import get_user_model
from django.test import TestCase

from ai.services import (
    export_service,
    finalize_service,
    plan_service,
    promote_service,
    review_service,
    revise_service,
    write_service,
)
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


class ProposalServiceTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='service-user', password='pass')
        org = Organization.objects.create(name='Service Org', admin=user)
        self.proposal = Proposal.objects.create(author=user, org=org, content={'meta': {'title': 'Service Proposal'}})
        self.section = ProposalSection.objects.create(proposal=self.proposal, key='intro', title='Introduction')

    def test_plan_service_is_idempotent(self):
        blueprint = [{'section_key': 'intro', 'title': 'Introduction', 'questions': ['Goal?']}]
        self.assertEqual(plan_service(proposal_id=self.proposal.id, blueprint=blueprint), [])
        self.assertEqual(ProposalSection.objects.filter(proposal=self.proposal).count(), 1)

    def test_write_and_revise_services_keep_approved_content_unchanged(self):
        write_service(section=self.section, draft_markdown='First draft', answers={'goal': 'Test'})
        revise_service(
            section=self.section,
            revised_text='Revised draft',
            user_id=1,
            from_text='First draft',
            diff={'change_ratio': 0.4, 'blocks': []},
        )
        self.section.refresh_from_db()
        self.assertEqual(self.section.draft_content, 'Revised draft')
        self.assertEqual(self.section.approved_content, '')
        self.assertEqual(len(self.section.revisions), 1)

    def test_review_service_requires_human_review_for_invalid_result(self):
        result = review_service({'section_key': 'intro', 'decision': 'unknown'})
        self.assertEqual(result['decision'], 'human_review')

    def test_promote_finalize_and_export_services_share_approved_source(self):
        self.section.draft_content = 'Approved body'
        self.section.save(update_fields=['draft_content'])
        promote_service(section=self.section)
        source = finalize_service(proposal=self.proposal)
        self.assertIn('Approved body', source)
        formatted = finalize_service(proposal=self.proposal, final_markdown='Formatted body')
        self.assertEqual(formatted, 'Formatted body')
        self.assertEqual(export_service(proposal=self.proposal), 'Formatted body')
