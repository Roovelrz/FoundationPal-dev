import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from orgs.models import Organization, OrgUser
from proposals.finalization import get_export_markdown
from proposals.models import Proposal, ProposalSection


class FinalMarkdownExportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='exporter', password='p')
        self.org = Organization.objects.create(name='Export Org', admin=self.user)
        OrgUser.objects.create(org=self.org, user=self.user, role='admin')
        self.proposal = Proposal.objects.create(
            author=self.user,
            org=self.org,
            content={'meta': {'title': 'Legacy title'}},
            final_markdown='# Final title\n\nExact formatter output',
        )
        self.section = ProposalSection.objects.create(
            proposal=self.proposal,
            key='summary',
            title='Summary',
            order=1,
            state='approved',
            approved_content='Approved fallback',
            content='Approved fallback',
            locked=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(user=self.user)

    def test_export_uses_exact_saved_final_markdown(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.api.post(
                    '/api/exports',
                    {'proposal_id': self.proposal.id, 'format': 'md'},
                    format='json',
                    HTTP_X_ORG_ID=str(self.org.id),
                )

                self.assertEqual(response.status_code, 200, response.content)
                path = response.json()['url'].removeprefix('/media/')
                with default_storage.open(path, 'rb') as exported:
                    self.assertEqual(exported.read().decode('utf-8'), self.proposal.final_markdown)

    def test_all_export_formats_work_without_an_explicit_workspace_header(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                for export_format in ('md', 'pdf', 'docx'):
                    with self.subTest(export_format=export_format):
                        response = self.api.post(
                            '/api/exports',
                            {'proposal_id': self.proposal.id, 'format': export_format},
                            format='json',
                        )

                        self.assertEqual(response.status_code, 200, response.content)
                        self.assertTrue(response.json()['url'])

    def test_export_falls_back_to_approved_sections(self):
        self.proposal.final_markdown = ''
        self.proposal.save(update_fields=['final_markdown'])

        markdown = get_export_markdown(self.proposal)

        self.assertIn('# Legacy title', markdown)
        self.assertIn('## Summary', markdown)
        self.assertIn('Approved fallback', markdown)

    def test_export_rejects_unapproved_sections(self):
        self.section.state = 'draft'
        self.section.save(update_fields=['state'])

        response = self.api.post(
            '/api/exports',
            {'proposal_id': self.proposal.id, 'format': 'md'},
            format='json',
            HTTP_X_ORG_ID=str(self.org.id),
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['error'], 'sections_not_approved')
