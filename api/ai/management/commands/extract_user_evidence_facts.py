import re

from django.core.management.base import BaseCommand

from ai.models import EvidenceFact, UserEvidence


class Command(BaseCommand):
    help = 'Create review-required, source-grounded facts for user evidence records.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-id', default='')

    def handle(self, *args, **options):
        evidence = UserEvidence.objects.select_related('chunk', 'resource')
        if options['organization_id']:
            evidence = evidence.filter(organization_id=str(options['organization_id']))
        created = 0
        for item in evidence:
            if item.facts.exists():
                continue
            source = (item.controlled_summary or item.chunk.text).strip()
            if not source:
                continue
            role = 'unknown'
            if re.search(r'主持|负责人', source):
                role = 'lead'
            elif re.search(r'第一作者', source):
                role = 'first_author'
            elif re.search(r'参与|成员', source):
                role = 'participant'
            status = 'completed' if re.search(r'已发表|完成|获批|结题', source) else 'uncertain'
            EvidenceFact.objects.create(
                user_evidence=item,
                subject=item.resource.display_name,
                predicate='source_grounded_evidence',
                object=source[:4000],
                fact_type=item.chunk.chunk_type or 'unclassified',
                fact_status=status,
                user_role=role,
                verification_status='extracted',
            )
            created += 1
        self.stdout.write(self.style.SUCCESS(f'created_facts={created}'))
