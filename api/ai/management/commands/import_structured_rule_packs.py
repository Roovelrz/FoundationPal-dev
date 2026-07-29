import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ai.ingestion import create_resource_with_chunks
from ai.domain_indexing import reindex_domain_resource
from ai.models import GrantPack, GrantPackDocument, GrantPackVersion, GrantProgram, GrantRequirement, SectionSchema


TYPE_MAP = {'eligibility': 'eligibility', 'budget': 'budget', 'submission': 'submission', 'review': 'review', 'format': 'format'}


class Command(BaseCommand):
    help = 'Import structured grant rule packs and their local source text.'

    def add_arguments(self, parser):
        parser.add_argument('--root', required=True)

    def handle(self, *args, **options):
        root = Path(options['root'])
        if not root.is_dir():
            raise CommandError('rule_pack_root_not_found')
        imported = []
        with transaction.atomic():
            for pack_path in sorted(root.glob('*/pack.json')):
                payload = json.loads(pack_path.read_text(encoding='utf-8'))
                program_data = payload['program']
                program_type = program_data.get('type') or ('teaching_reform' if 'teaching' in payload['pack_id'] else 'general')
                region = program_data.get('jurisdiction', '')
                program, _ = GrantProgram.objects.get_or_create(
                    name=program_data['family'], program_type=program_type, region=region,
                    defaults={'authority': program_data['issuer']},
                )
                pack, _ = GrantPack.objects.get_or_create(
                    code=payload['pack_id'], defaults={'program': program, 'name': program_data['family']},
                )
                version, _ = GrantPackVersion.objects.get_or_create(
                    pack=pack, year=program_data['year'], version=payload['version'],
                    defaults={'detected_metadata': {'unresolved_items': payload.get('unresolved_items', []), 'sources': payload['sources']}},
                )
                source_chunks = []
                for text_file in sorted((pack_path.parent / 'source_documents').glob('*.txt')):
                    text = text_file.read_text(encoding='utf-8', errors='replace')
                    resource = create_resource_with_chunks(
                        type_='guideline', title=text_file.name, source_url='', full_text=text,
                        knowledge_domain='grant_rule',
                    )
                    resource.grant_pack = pack
                    resource.classification_status = 'pack_draft'
                    resource.metadata = {**(resource.metadata or {}), 'year': program_data['year'], 'program_type': program_type, 'pack_id': payload['pack_id']}
                    resource.save(update_fields=['grant_pack', 'classification_status', 'metadata'])
                    reindex_domain_resource(resource=resource)
                    GrantPackDocument.objects.get_or_create(pack_version=version, resource=resource, defaults={'document_type': 'guide'})
                    source_chunks.extend(resource.chunks.order_by('chunk_index'))
                if not source_chunks:
                    raise CommandError(f'pack_source_text_missing:{payload["pack_id"]}')
                section_map = {}
                for index, section in enumerate(payload.get('section_schema', []), start=1):
                    section_map[section['section_key']] = SectionSchema.objects.update_or_create(
                        pack_version=version, section_key=section['section_key'],
                        defaults={'source_chunk': source_chunks[0], 'title': section['title'], 'order': index, 'required': section.get('status') == 'template_required', 'field_type': section.get('status', 'markdown')},
                    )[0]
                for index, requirement in enumerate(payload['requirements']):
                    item, _ = GrantRequirement.objects.update_or_create(
                        pack_version=version, source_chunk=source_chunks[index % len(source_chunks)], text=requirement['rule'],
                        defaults={'requirement_type': TYPE_MAP.get(requirement['type'], 'content'), 'mandatory': requirement.get('severity') in {'blocking', 'conditional_blocking'}, 'target_section': requirement.get('section_key', ''), 'validation_method': requirement.get('type', ''), 'applicability': {'source_id': requirement.get('source', ''), 'category': requirement.get('category', ''), 'severity': requirement.get('severity', '')}, 'source_excerpt': requirement['rule'], 'extraction_prompt_version': 0},
                    )
                    if item.target_section in section_map:
                        item.target_sections.add(section_map[item.target_section])
                version.status = 'needs_review' if payload.get('unresolved_items') and 'teaching_reform' in payload['pack_id'] else 'published'
                version.detected_metadata = {**(version.detected_metadata or {}), 'unresolved_items': payload.get('unresolved_items', []), 'imported_from': str(pack_path)}
                version.save(update_fields=['status', 'detected_metadata'])
                imported.append({'pack_id': payload['pack_id'], 'version_id': version.id, 'status': version.status, 'requirements': len(payload['requirements']), 'sections': len(section_map)})
        self.stdout.write(json.dumps({'imported': imported}, ensure_ascii=False))
