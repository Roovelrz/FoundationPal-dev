from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from celery import shared_task

from .models import ExportJob
from .utils import render_pdf_from_text, render_docx_from_markdown
from proposals.finalization import SectionsNotApproved
from ai.services import export_service


@shared_task
def perform_export(job_id: int):
    job = ExportJob.objects.select_related('proposal').get(id=job_id)
    proposal = job.proposal
    try:
        md = export_service(proposal=proposal)
    except SectionsNotApproved:
        job.status = 'error'
        job.error = 'sections_not_approved'
        job.save(update_fields=['status', 'error'])
        return
    checksum = ''
    if job.format == 'md':
        data = md.encode('utf-8')
        try:
            from app.common.files import compute_checksum

            checksum = compute_checksum(data).hex
        except Exception:
            import hashlib as _hl

            checksum = _hl.sha256(data).hexdigest()
        ext = 'md'
    elif job.format == 'pdf':
        data, checksum = render_pdf_from_text(md)
        ext = 'pdf'
    else:
        data, checksum = render_docx_from_markdown(md)
        ext = 'docx'
    path = f'exports/proposal-{proposal.id}-{job.id}.{ext}'
    default_storage.save(path, ContentFile(data))
    url = f'{settings.MEDIA_URL}{path}'
    job.status = 'done'
    job.url = url
    job.checksum = checksum or ''
    job.save(update_fields=['status', 'url', 'checksum'])
    try:
        proposal.downloads = (proposal.downloads or 0) + 1
        proposal.save(update_fields=['downloads'])
    except Exception:
        pass
