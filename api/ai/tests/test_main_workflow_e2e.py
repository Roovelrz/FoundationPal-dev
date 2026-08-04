import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from docx import Document
from rest_framework.test import APIClient

from orgs.models import Organization, OrgUser
from proposals.models import Proposal, ProposalSection


@override_settings(
    DEBUG=True,
    AI_PROVIDER='stub',
    AI_ASYNC=False,
    EXPORTS_ASYNC=False,
)
class MainWorkflowE2ETests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='e2e-user', password='p')
        self.org = Organization.objects.create(name='E2E Org', admin=self.user)
        OrgUser.objects.create(org=self.org, user=self.user, role='admin')
        self.api = APIClient()
        self.api.force_authenticate(user=self.user)
        self.org_header = {'HTTP_X_ORG_ID': str(self.org.id)}

    def test_create_plan_write_revise_approve_format_and_export_docx(self):
        create_response = self.api.post(
            '/api/proposals/',
            {'content': {'meta': {'title': 'Verified Fund Proposal'}}},
            format='json',
            **self.org_header,
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        proposal_id = create_response.json()['id']

        plan_response = self.api.post(
            '/api/ai/plan',
            {'proposal_id': proposal_id, 'text_spec': 'Verified grant workflow'},
            format='json',
            **self.org_header,
        )
        self.assertEqual(plan_response.status_code, 200, plan_response.content)
        self.assertEqual(
            plan_response.json()['created_sections'],
            ['summary', 'narrative', 'budget'],
        )

        sections = list(
            ProposalSection.objects.filter(proposal_id=proposal_id).order_by('order', 'id')
        )
        self.assertEqual([section.key for section in sections], ['summary', 'narrative', 'budget'])

        revised_text = ''
        for index, section in enumerate(sections):
            write_response = self.api.post(
                '/api/ai/write',
                {
                    'proposal_id': proposal_id,
                    'section_id': section.key,
                    'answers': {'objective': f'Verify {section.key}'},
                },
                format='json',
                **self.org_header,
            )
            self.assertEqual(write_response.status_code, 200, write_response.content)
            draft_text = write_response.json()['draft_text']

            if index == 0:
                revise_response = self.api.post(
                    '/api/ai/revise',
                    {
                        'proposal_id': proposal_id,
                        'section_id': section.key,
                        'base_text': draft_text,
                        'change_request': 'Add verified evidence',
                    },
                    format='json',
                    **self.org_header,
                )
                self.assertEqual(revise_response.status_code, 200, revise_response.content)
                revised_text = revise_response.json()['draft_text']

            promote_response = self.api.post(
                f'/api/sections/{section.id}/promote',
                {},
                format='json',
                **self.org_header,
            )
            self.assertEqual(promote_response.status_code, 200, promote_response.content)

        detail_response = self.api.get(
            f'/api/proposals/{proposal_id}/',
            **self.org_header,
        )
        self.assertEqual(detail_response.status_code, 200, detail_response.content)
        self.assertTrue(
            all(
                section['state'] == 'approved' and section['locked']
                for section in detail_response.json()['sections']
            )
        )

        full_draft_response = self.api.get(
            f'/api/ai/proposals/{proposal_id}/full-draft',
            **self.org_header,
        )
        self.assertEqual(full_draft_response.status_code, 200, full_draft_response.content)
        full_draft = full_draft_response.json()
        full_task_response = self.api.post(
            '/api/ai/human-tasks',
            {
                'proposal_id': proposal_id,
                'node': 'final_export_confirmation',
                'thread_id': f'full-draft-{proposal_id}-{full_draft["version"]}',
                'input': {
                    'kind': 'full_draft',
                    'draft_title': '审批后全文草稿',
                    'draft_version': full_draft['version'],
                    'draft_text': full_draft['draft_text'],
                },
            },
            format='json',
            **self.org_header,
        )
        self.assertEqual(full_task_response.status_code, 201, full_task_response.content)
        full_task = full_task_response.json()
        full_approval_response = self.api.post(
            f'/api/ai/human-tasks/{full_task["id"]}/decision',
            {'thread_id': full_task['thread_id'], 'action': 'approve'},
            format='json',
            **self.org_header,
        )
        self.assertEqual(full_approval_response.status_code, 200, full_approval_response.content)

        format_response = self.api.post(
            '/api/ai/format',
            {'proposal_id': proposal_id, 'template_hint': 'standard'},
            format='json',
            **self.org_header,
        )
        self.assertEqual(format_response.status_code, 200, format_response.content)
        formatted_text = format_response.json()['formatted_text']
        self.assertIn(revised_text, formatted_text)

        proposal = Proposal.objects.get(id=proposal_id)
        self.assertEqual(proposal.final_markdown, formatted_text)
        refreshed_response = self.api.get(
            f'/api/proposals/{proposal_id}/',
            **self.org_header,
        )
        self.assertEqual(
            refreshed_response.json()['final_markdown'],
            formatted_text,
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                export_response = self.api.post(
                    '/api/exports',
                    {'proposal_id': proposal_id, 'format': 'docx'},
                    format='json',
                    **self.org_header,
                )
                self.assertEqual(export_response.status_code, 200, export_response.content)
                self.assertEqual(export_response.json()['status'], 'done')
                self.assertEqual(len(export_response.json()['checksum']), 64)

                path = export_response.json()['url'].removeprefix('/media/')
                with default_storage.open(path, 'rb') as exported:
                    document = Document(exported)
                exported_text = '\n'.join(paragraph.text for paragraph in document.paragraphs)
                self.assertIn('Verified Fund Proposal', exported_text)
                self.assertIn(revised_text, exported_text)

        proposal.refresh_from_db()
        self.assertEqual(proposal.downloads, 1)
