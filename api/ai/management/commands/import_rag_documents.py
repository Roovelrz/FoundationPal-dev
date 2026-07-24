import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ai.ingestion import PARSER_VERSION, ingest_pdf
from ai.models import AIResource


SOURCE_TYPES = {'guideline', 'call_snapshot', 'successful_case', 'team_profile', 'template', 'review_criteria'}
EVIDENCE_PURPOSES = {'constraint', 'fact', 'style', 'template'}
REQUIRED_FIELDS = {'filename', 'display_name', 'source_type', 'evidence_purpose', 'proposal_scope', 'notes'}


@dataclass(frozen=True)
class ManifestItem:
    row_number: int
    filename: str
    display_name: str
    source_type: str
    evidence_purpose: str
    proposal_scope: str
    notes: str
    content: bytes
    sha256: str
    existing_id: int | None


class Command(BaseCommand):
    help = 'Import RAG PDFs listed in a CSV manifest.'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', required=True)
        parser.add_argument('--pdf-dir', required=True)
        parser.add_argument('--organization-id', default='')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        manifest_path = self._resolve_path(options['manifest'])
        pdf_dir = self._resolve_path(options['pdf_dir'])
        organization_id = options['organization_id']
        if not manifest_path.is_file():
            raise CommandError(f'manifest_not_found: {manifest_path}')
        if not pdf_dir.is_dir():
            raise CommandError(f'pdf_dir_not_found: {pdf_dir}')

        items = self._read_manifest(manifest_path, pdf_dir, organization_id)
        self.stdout.write('预览：')
        for item in items:
            action = '更新' if item.existing_id else '新建'
            self.stdout.write(
                f'{item.filename} | {item.source_type} | {item.evidence_purpose} | '
                f'已存在={bool(item.existing_id)} | 将{action}'
            )
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS('预览完成，未写入数据库。'))
            return

        with transaction.atomic():
            for item in items:
                metadata = {'proposal_scope': item.proposal_scope, 'notes': item.notes}
                if item.existing_id:
                    AIResource.objects.filter(pk=item.existing_id).update(
                        source_type=item.source_type,
                        evidence_purpose=item.evidence_purpose,
                        title=item.display_name[:256],
                        display_name=item.display_name[:256],
                        original_filename=item.filename[:512],
                        mime_type='application/pdf',
                        is_deleted=False,
                        status='ready',
                        error_code='',
                        metadata=metadata,
                    )
                    continue
                resource = ingest_pdf(
                    content=item.content,
                    filename=item.filename,
                    organization_id=organization_id,
                    source_type=item.source_type,
                    evidence_purpose=item.evidence_purpose,
                    resource_sha256=item.sha256,
                )
                resource.title = item.display_name[:256]
                resource.display_name = item.display_name[:256]
                resource.metadata = metadata
                resource.save(update_fields=['title', 'display_name', 'metadata'])
        self.stdout.write(self.style.SUCCESS(f'导入完成：{len(items)} 个文档。'))

    @staticmethod
    def _resolve_path(value: str) -> Path:
        path = Path(value)
        if path.is_absolute() or path.exists():
            return path
        return Path(settings.BASE_DIR).parent / path

    def _read_manifest(self, manifest_path: Path, pdf_dir: Path, organization_id: str) -> list[ManifestItem]:
        try:
            with manifest_path.open('r', encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                headers = set(reader.fieldnames or [])
                missing = REQUIRED_FIELDS - headers
                if missing:
                    raise CommandError(f'manifest_missing_fields: {", ".join(sorted(missing))}')
                rows = list(reader)
        except UnicodeDecodeError as exc:
            raise CommandError('manifest_encoding_invalid: expected UTF-8 or UTF-8 BOM') from exc
        if not rows:
            raise CommandError('manifest_empty')

        seen: set[tuple[str, str, str]] = set()
        items: list[ManifestItem] = []
        for number, row in enumerate(rows, start=2):
            filename = (row.get('filename') or '').strip()
            display_name = (row.get('display_name') or '').strip()
            source_type = (row.get('source_type') or '').strip()
            evidence_purpose = (row.get('evidence_purpose') or '').strip()
            proposal_scope = (row.get('proposal_scope') or '').strip()
            notes = (row.get('notes') or '').strip()
            if not filename or not display_name:
                raise CommandError(f'row_{number}_required_field_missing')
            if source_type not in SOURCE_TYPES:
                raise CommandError(f'row_{number}_invalid_source_type: {source_type}')
            if evidence_purpose not in EVIDENCE_PURPOSES:
                raise CommandError(f'row_{number}_invalid_evidence_purpose: {evidence_purpose}')
            pdf_path = pdf_dir / filename
            if not pdf_path.is_file():
                raise CommandError(f'row_{number}_pdf_not_found: {pdf_path}')
            content = pdf_path.read_bytes()
            sha256 = hashlib.sha256(content).hexdigest()
            identity = (organization_id, sha256, PARSER_VERSION)
            if identity in seen:
                raise CommandError(f'row_{number}_duplicate_conflict: {filename}')
            seen.add(identity)
            existing_id = AIResource.objects.filter(
                organization_id=organization_id,
                sha256=sha256,
                parser_version=PARSER_VERSION,
            ).values_list('id', flat=True).first()
            items.append(ManifestItem(number, filename, display_name, source_type, evidence_purpose, proposal_scope, notes, content, sha256, existing_id))
        return items
