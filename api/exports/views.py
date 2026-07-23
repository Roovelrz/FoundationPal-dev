from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse  # noqa: F401
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.db import models

from proposals.models import Proposal
from proposals.finalization import SectionsNotApproved, get_export_markdown
from .models import ExportJob
from .utils import render_pdf_from_text, render_docx_from_markdown
from .tasks import perform_export


def _accessible_proposals(request):
    user = getattr(request, 'user', None)
    if not getattr(user, 'is_authenticated', False):
        return Proposal.objects.none()
    queryset = Proposal.objects.filter(
        models.Q(org__admin=user) | models.Q(org__memberships__user=user)
    ).distinct()
    org_id = request.headers.get('X-Org-ID')
    if org_id and str(org_id).isdigit():
        queryset = queryset.filter(org_id=int(org_id))
    return queryset


@api_view(['POST'])
@permission_classes([AllowAny if settings.DEBUG else IsAuthenticated])
def create_export(request):
    proposal_id = request.data.get('proposal_id')
    fmt = (request.data.get('format') or 'md').lower()
    if fmt not in ('md', 'pdf', 'docx'):
        return Response({'error': 'invalid_format'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        proposal = _accessible_proposals(request).get(id=proposal_id)
    except Proposal.DoesNotExist:
        return Response({'error': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        md = get_export_markdown(proposal)
    except SectionsNotApproved:
        return Response({'error': 'sections_not_approved'}, status=status.HTTP_409_CONFLICT)

    job = ExportJob.objects.create(proposal=proposal, format=fmt, status='pending')
    # Async path when enabled and broker configured
    if getattr(settings, 'EXPORTS_ASYNC', False) and getattr(settings, 'CELERY_BROKER_URL', ''):
        try:
            perform_export.delay(job.id)
            return Response({'id': job.id, 'status': job.status})
        except Exception:
            # Fall through to sync if enqueue fails
            pass

    # Synchronous render (default)
    checksum = ''
    if fmt == 'md':
        data = md.encode('utf-8')
        ext = 'md'
        try:
            from app.common.files import compute_checksum

            checksum = compute_checksum(data).hex
        except Exception:
            import hashlib as _hl

            checksum = _hl.sha256(data).hexdigest()
    elif fmt == 'pdf':
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
    # Increment proposal downloads counter
    try:
        proposal.downloads = (proposal.downloads or 0) + 1
        proposal.save(update_fields=['downloads'])
    except Exception:
        pass
    return Response({'id': job.id, 'status': job.status, 'url': job.url, 'checksum': job.checksum})


@api_view(['GET'])
@permission_classes([AllowAny if settings.DEBUG else IsAuthenticated])
def get_export(request, job_id: int):
    try:
        proposal_ids = _accessible_proposals(request).values_list('id', flat=True)
        job = ExportJob.objects.select_related('proposal').get(
            id=job_id,
            proposal_id__in=proposal_ids,
        )
    except ExportJob.DoesNotExist:
        return Response({'error': 'not_found'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'id': job.id, 'status': job.status, 'url': job.url, 'format': job.format})
