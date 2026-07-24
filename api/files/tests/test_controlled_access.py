from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from files.models import FileUpload
from files.services import FileAccessError, read_controlled_upload
from orgs.models import Organization, OrgUser
from proposals.models import Proposal


class ControlledFileAccessTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='file-owner', password='pass')
        self.member = get_user_model().objects.create_user(username='file-member', password='pass')
        self.org = Organization.objects.create(name='File Org', admin=self.owner)
        OrgUser.objects.create(org=self.org, user=self.member, role='member')
        self.proposal = Proposal.objects.create(author=self.owner, org=self.org)
        self.upload = FileUpload.objects.create(
            owner=self.owner,
            organization=self.org,
            proposal=self.proposal,
            file=ContentFile(b'%PDF-controlled', name='controlled.pdf'),
            content_type='application/pdf',
            size=15,
        )

    def test_owner_reads_only_by_scoped_file_id(self):
        upload, content = read_controlled_upload(
            file_id=self.upload.id,
            caller=self.owner,
            organization_id=self.org.id,
            proposal_id=self.proposal.id,
        )
        self.assertEqual(upload.id, self.upload.id)
        self.assertEqual(content, b'%PDF-controlled')

    def test_member_cannot_read_another_users_upload(self):
        with self.assertRaisesRegex(FileAccessError, 'file_not_owned'):
            read_controlled_upload(
                file_id=self.upload.id,
                caller=self.member,
                organization_id=self.org.id,
            )

    def test_cross_workspace_is_rejected(self):
        other_org = Organization.objects.create(name='Other File Org', admin=self.owner)
        with self.assertRaisesRegex(FileAccessError, 'workspace_forbidden'):
            read_controlled_upload(
                file_id=self.upload.id,
                caller=self.owner,
                organization_id=other_org.id,
            )

    def test_unscoped_legacy_upload_is_not_mcp_eligible(self):
        legacy = FileUpload.objects.create(
            owner=self.owner,
            file=ContentFile(b'legacy', name='legacy.txt'),
            content_type='text/plain',
            size=6,
        )
        with self.assertRaisesRegex(FileAccessError, 'file_not_scoped'):
            read_controlled_upload(file_id=legacy.id, caller=self.owner, organization_id=self.org.id)

    def test_upload_endpoint_binds_organization_and_proposal(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.post(
            '/api/files',
            {
                'file': SimpleUploadedFile('scoped.txt', b'scoped content', content_type='text/plain'),
                'proposal_id': str(self.proposal.id),
            },
            format='multipart',
            HTTP_X_ORG_ID=str(self.org.id),
        )
        self.assertEqual(response.status_code, 200, response.content)
        upload = FileUpload.objects.get(id=response.data['id'])
        self.assertEqual(upload.organization_id, self.org.id)
        self.assertEqual(upload.proposal_id, self.proposal.id)
