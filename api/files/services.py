'''Controlled file access for document ingestion and future MCP tools.'''

from __future__ import annotations

from django.core.files.uploadedfile import UploadedFile

from .models import FileUpload


class FileAccessError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def get_controlled_upload(*, file_id: int, caller, organization_id: int, proposal_id: int | None = None) -> FileUpload:
    '''Return only an owned, organization-bound upload addressed by file_id.'''
    upload = FileUpload.objects.select_related('organization', 'proposal', 'owner').filter(id=file_id).first()
    if upload is None:
        raise FileAccessError('file_not_found')
    if upload.organization_id is None:
        raise FileAccessError('file_not_scoped')
    if upload.organization_id != organization_id:
        raise FileAccessError('workspace_forbidden')
    if upload.owner_id != getattr(caller, 'id', None):
        raise FileAccessError('file_not_owned')
    if proposal_id is not None and upload.proposal_id != proposal_id:
        raise FileAccessError('proposal_forbidden')
    return upload


def read_controlled_upload(*, file_id: int, caller, organization_id: int, proposal_id: int | None = None) -> tuple[FileUpload, bytes]:
    '''Read bytes through storage only after controlled file_id authorization.'''
    upload = get_controlled_upload(
        file_id=file_id,
        caller=caller,
        organization_id=organization_id,
        proposal_id=proposal_id,
    )
    with upload.file.open('rb') as handle:
        return upload, handle.read()
