"""Ordinary-user project setup and scoped material ingestion."""

from __future__ import annotations

import os

from django.db import transaction

from .ingestion import IngestionError, _chunk_text, _normalize_text, create_resource_with_chunks
from .models import AIResource, EvidenceFact, UserEvidence


PROJECT_MATERIAL_PARSER_VERSION = 'project-material-v2'
PAGE_METADATA_VERSION = 'project-material-pages-v1'


class ProjectMaterialError(ValueError):
    pass


def _page_chunks_from_pages(pages):
    return [
        (page_number, chunk, '')
        for page_number, page_text in pages
        for chunk in _chunk_text(page_text)
        if chunk.strip()
    ]


def _extract_pdf_pages(path):
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer

        pages = []
        for page_number, layout in enumerate(extract_pages(path), start=1):
            text = _normalize_text(''.join(
                item.get_text() for item in layout if isinstance(item, LTTextContainer)
            ))
            if text:
                pages.append((page_number, text))
        return pages
    except Exception:
        return []


def _extract_docx_pages(path):
    try:
        from docx import Document
        from docx.oxml.ns import qn

        document = Document(path)
        pages = []
        page_number = 1
        current = []

        def finish_page():
            nonlocal page_number, current
            text = _normalize_text('\n'.join(current))
            if text:
                pages.append((page_number, text))
            page_number += 1
            current = []

        for paragraph in document.paragraphs:
            if paragraph.paragraph_format.page_break_before and current:
                finish_page()
            text = ''
            for element in paragraph._p.iter():
                if element.tag == qn('w:t'):
                    text += element.text or ''
                    continue
                is_page_break = element.tag == qn('w:lastRenderedPageBreak') or (
                    element.tag == qn('w:br') and element.get(qn('w:type')) == 'page'
                )
                if is_page_break:
                    normalized = _normalize_text(text)
                    if normalized:
                        current.append(normalized)
                    text = ''
                    finish_page()
            normalized = _normalize_text(text)
            if normalized:
                current.append(normalized)
        if current:
            finish_page()
        return pages
    except Exception:
        return []


def extract_uploaded_material(path, mime_type):
    """Return upload text plus page-aware chunks when the file format retains pages."""
    path = str(path or '')
    if not path or not os.path.isfile(path):
        return '', []
    is_pdf = mime_type == 'application/pdf' or path.lower().endswith('.pdf')
    is_docx = (
        mime_type in {
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/msword',
        }
        or path.lower().endswith('.docx')
    )
    pages = _extract_pdf_pages(path) if is_pdf else (_extract_docx_pages(path) if is_docx else [])
    if pages:
        text = '\n'.join(page_text for _, page_text in pages)[:50000]
        return text, _page_chunks_from_pages(pages)
    if is_pdf or is_docx:
        return '', []
    try:
        with open(path, 'rb') as source:
            text = source.read(50000).decode('utf-8', errors='ignore').strip()
    except OSError:
        return '', []
    return text, _page_chunks_from_pages([(1, text)]) if text else []


def _resources(proposal, knowledge_domain):
    return AIResource.objects.filter(
        organization_id=str(proposal.org_id),
        proposal_id=proposal.id,
        knowledge_domain=knowledge_domain,
        is_deleted=False,
    )


def _file_records(proposal, knowledge_domain):
    return [
        {
            'id': resource.id,
            'name': resource.original_filename or resource.display_name or resource.title,
            'uploaded_at': resource.created_at.isoformat(),
            'chunk_count': resource.chunks.count(),
        }
        for resource in _resources(proposal, knowledge_domain)
        .exclude(original_filename='')
        .order_by('created_at', 'id')
    ]


def _restore_uploaded_filenames(proposal):
    """Recover display names for legacy project materials from their upload rows."""
    from files.models import FileUpload
    from .ingestion import _normalize_text

    uploads = list(FileUpload.objects.filter(proposal=proposal).exclude(ocr_text='').order_by('id'))
    if not uploads:
        return
    for resource in AIResource.objects.filter(
        organization_id=str(proposal.org_id),
        proposal_id=proposal.id,
        knowledge_domain__in=['grant_rule', 'user_evidence'],
        is_deleted=False,
    ):
        filename = ''
        for upload in uploads:
            if AIResource.compute_sha256(_normalize_text(upload.ocr_text)) == resource.sha256:
                filename = os.path.basename(upload.file.name or '')
                break
        if filename and (resource.original_filename != filename or resource.display_name != filename):
            resource.original_filename = filename[:512]
            resource.display_name = filename[:256]
            resource.title = filename[:256]
            resource.save(update_fields=['original_filename', 'display_name', 'title'])


def _page_span_for_chunk(chunk_text, page_chunks):
    text = _normalize_text(chunk_text)
    if not text:
        return None
    samples = [text[:80], text[max(0, len(text) // 2 - 40):len(text) // 2 + 40], text[-80:]]
    samples = [sample[:32] for sample in samples if len(sample) >= 12]
    matched_pages = []
    for page_number, page_text, _ in page_chunks:
        normalized_page = _normalize_text(page_text)
        if any(sample in normalized_page for sample in samples):
            matched_pages.append(page_number)
    if not matched_pages:
        return None
    return min(matched_pages), max(matched_pages)


def repair_uploaded_material_pages(proposal):
    """Backfill page metadata for earlier uploads that were flattened to plain text."""
    from files.models import FileUpload

    uploads = list(FileUpload.objects.filter(proposal=proposal).exclude(ocr_text='').order_by('id'))
    if not uploads:
        return
    resources = AIResource.objects.filter(
        organization_id=str(proposal.org_id),
        proposal_id=proposal.id,
        knowledge_domain__in=['grant_rule', 'user_evidence'],
        is_deleted=False,
    ).exclude(original_filename='').prefetch_related('chunks')
    for resource in resources:
        metadata = dict(resource.metadata or {})
        if metadata.get('page_metadata_version') == PAGE_METADATA_VERSION:
            continue
        matched = None
        for upload in uploads:
            path = getattr(upload.file, 'path', '')
            text, page_chunks = extract_uploaded_material(path, upload.content_type)
            if not page_chunks:
                continue
            same_text = AIResource.compute_sha256(_normalize_text(text)) == resource.sha256
            if same_text:
                matched = page_chunks
                break
        if not matched:
            continue
        for chunk in resource.chunks.all():
            page_span = _page_span_for_chunk(chunk.text, matched)
            if page_span and (chunk.page_start, chunk.page_end) != page_span:
                chunk.page_start, chunk.page_end = page_span
                chunk.save(update_fields=['page_start', 'page_end'])
        metadata['source_origin'] = 'uploaded_file'
        metadata['page_metadata_version'] = PAGE_METADATA_VERSION
        resource.metadata = metadata
        resource.save(update_fields=['metadata'])


def _upgrade_legacy_project_materials(proposal):
    """Replace only oversized legacy project chunks while retaining old evidence snapshots."""
    legacy = list(
        AIResource.objects.filter(
            organization_id=str(proposal.org_id),
            proposal_id=proposal.id,
            knowledge_domain__in=['grant_rule', 'user_evidence'],
            is_deleted=False,
        ).exclude(parser_version=PROJECT_MATERIAL_PARSER_VERSION).prefetch_related('chunks')
    )
    for resource in legacy:
        chunks = list(resource.chunks.order_by('chunk_index'))
        if not chunks or max(len(chunk.text or '') for chunk in chunks) <= 1000:
            continue
        replacement = create_project_material(
            proposal=proposal,
            owner=resource.owner_user,
            material_kind='guideline' if resource.knowledge_domain == 'grant_rule' else 'evidence',
            title=resource.display_name or resource.title,
            original_filename=resource.original_filename,
            mime_type=resource.mime_type or 'text/plain',
            text='\n'.join(chunk.text for chunk in chunks),
        )
        if replacement.pk != resource.pk:
            resource.is_deleted = True
            resource.status = 'deleted'
            resource.save(update_fields=['is_deleted', 'status'])


def _retire_replaced_resource(proposal, resource_id, replacement_text):
    if not resource_id:
        return
    previous = AIResource.objects.filter(
        pk=resource_id,
        organization_id=str(proposal.org_id),
        proposal_id=proposal.id,
        is_deleted=False,
    ).first()
    if previous is not None and previous.sha256 != AIResource.compute_sha256(replacement_text):
        previous.is_deleted = True
        previous.status = 'deleted'
        previous.save(update_fields=['is_deleted', 'status'])


@transaction.atomic
def create_project_material(*, proposal, owner, material_kind, title, text, original_filename='', mime_type='text/plain', page_chunks=None):
    if material_kind not in {'guideline', 'evidence'}:
        raise ProjectMaterialError('material_kind_invalid')
    text = str(text or '').strip()
    if not text:
        raise ProjectMaterialError('document_text_unavailable')
    is_guideline = material_kind == 'guideline'
    try:
        resource = create_resource_with_chunks(
            type_='guideline' if is_guideline else 'team_profile',
            title=title or ('基金指南' if is_guideline else '用户材料'),
            source_url='',
            full_text=text,
            organization_id=str(proposal.org_id),
            proposal_id=proposal.id,
            evidence_purpose='constraint' if is_guideline else 'fact',
            original_filename=original_filename,
            mime_type=mime_type,
            knowledge_domain='grant_rule' if is_guideline else 'user_evidence',
            parser_version=PROJECT_MATERIAL_PARSER_VERSION,
            page_chunks=page_chunks or None,
        )
    except IngestionError as error:
        raise ProjectMaterialError(error.code) from error

    AIResource.objects.filter(pk=resource.pk).update(
        owner_user=owner if getattr(owner, 'is_authenticated', False) else None,
        authorization_scope='proposal',
        classification_status='pack_draft' if is_guideline else 'classified',
    )
    resource.refresh_from_db()
    metadata = dict(resource.metadata or {})
    metadata['source_origin'] = 'uploaded_file' if original_filename else 'project_setup'
    if page_chunks:
        metadata['page_metadata_version'] = PAGE_METADATA_VERSION
    resource.metadata = metadata
    resource.save(update_fields=['metadata'])
    if not is_guideline:
        for chunk in resource.chunks.order_by('chunk_index'):
            UserEvidence.objects.get_or_create(
                resource=resource,
                chunk=chunk,
                defaults={
                    'organization_id': str(proposal.org_id),
                    'proposal': proposal,
                    'owner_user': owner if getattr(owner, 'is_authenticated', False) else None,
                    'authorization_scope': 'proposal',
                    'controlled_summary': chunk.text[:1200],
                },
            )
    return resource


@transaction.atomic
def save_project_setup(*, proposal, owner, research_direction, core_problem='', guideline_text=''):
    research_direction = str(research_direction or '').strip()
    core_problem = str(core_problem or '').strip()
    guideline_text = str(guideline_text or '').strip()
    if not research_direction:
        raise ProjectMaterialError('research_direction_required')

    content = dict(proposal.content or {})
    meta = dict(content.get('meta') or {})
    previous_setup = dict(meta.get('user_setup') or {})
    saved_guideline_text = str(previous_setup.get('guideline_text') or '')
    if guideline_text:
        _retire_replaced_resource(proposal, previous_setup.get('pasted_guideline_resource_id'), guideline_text)
        guideline_resource = create_project_material(
            proposal=proposal,
            owner=owner,
            material_kind='guideline',
            title='用户粘贴的基金指南',
            text=guideline_text,
        )
        previous_setup['pasted_guideline_resource_id'] = guideline_resource.id
    else:
        guideline_text = saved_guideline_text
    if not _resources(proposal, 'grant_rule').exists():
        raise ProjectMaterialError('guideline_required')

    brief_text = f'研究方向：{research_direction}'
    if core_problem:
        brief_text += f'\n核心科学问题：{core_problem}'
    _retire_replaced_resource(proposal, previous_setup.get('brief_resource_id'), brief_text)
    brief_resource = create_project_material(
        proposal=proposal,
        owner=owner,
        material_kind='evidence',
        title='项目研究方向与核心问题',
        text=brief_text,
    )
    first_evidence = UserEvidence.objects.filter(resource=brief_resource, proposal=proposal).order_by('id').first()
    if first_evidence is not None:
        EvidenceFact.objects.get_or_create(
            user_evidence=first_evidence,
            subject='本项目',
            predicate='拟研究',
            object=research_direction if not core_problem else f'{research_direction}；核心科学问题：{core_problem}',
            fact_type='project_scope',
            defaults={
                'fact_status': 'planned',
                'user_role': 'unknown',
                'verification_status': 'user_confirmed',
            },
        )

    meta['user_setup'] = {
        'ready': True,
        'research_direction': research_direction,
        'core_problem': core_problem,
        'guideline_text': guideline_text,
        'brief_resource_id': brief_resource.id,
        'pasted_guideline_resource_id': previous_setup.get('pasted_guideline_resource_id'),
    }
    content['meta'] = meta
    proposal.content = content
    proposal.save(update_fields=['content', 'last_edited'])
    return project_setup_status(proposal)


def project_setup_status(proposal):
    _restore_uploaded_filenames(proposal)
    repair_uploaded_material_pages(proposal)
    _upgrade_legacy_project_materials(proposal)
    _restore_uploaded_filenames(proposal)
    setup = dict((proposal.content or {}).get('meta', {}).get('user_setup') or {})
    guideline_count = _resources(proposal, 'grant_rule').count()
    guideline_files = _file_records(proposal, 'grant_rule')
    evidence_files = _file_records(proposal, 'user_evidence')
    evidence_count = len(evidence_files)
    research_direction = str(setup.get('research_direction') or '')
    return {
        'proposal_id': proposal.id,
        'ready': bool(setup.get('ready') and research_direction and guideline_count),
        'research_direction': research_direction,
        'core_problem': str(setup.get('core_problem') or ''),
        'guideline_text': str(setup.get('guideline_text') or ''),
        'guideline_ready': bool(guideline_count),
        'guideline_count': guideline_count,
        'evidence_count': evidence_count,
        'guideline_files': guideline_files,
        'evidence_files': evidence_files,
    }


def project_planning_context(proposal):
    status = project_setup_status(proposal)
    if not status['ready']:
        return ''
    parts = [f'研究方向：{status["research_direction"]}']
    if status['core_problem']:
        parts.append(f'核心科学问题：{status["core_problem"]}')
    guide_chunks = []
    for resource in _resources(proposal, 'grant_rule').prefetch_related('chunks').order_by('id')[:3]:
        guide_chunks.extend(chunk.text for chunk in resource.chunks.order_by('chunk_index')[:3])
    if guide_chunks:
        parts.append('基金指南或申报要求：' + '\n'.join(guide_chunks)[:10000])
    return '\n\n'.join(parts)
