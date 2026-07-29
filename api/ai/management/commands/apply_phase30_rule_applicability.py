from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ai.models import GrantRequirement


OVERRIDES = {
    11: {'ethics_or_technology_safety': True},
    19: {'joint_application': True},
    20: {'out_of_province_affiliation': True},
    21: {'ethics_or_human_genetic_resource': True},
    24: {'program_category': 'youth_a'}, 25: {'program_category': 'youth_a'}, 26: {'program_category': 'youth_a'},
    27: {'program_category': 'youth_b'}, 28: {'program_category': 'youth_b'}, 29: {'program_category': 'youth_b'}, 30: {'program_category': 'youth_b'},
    39: {'program_category': 'major', 'completion_review': True},
}


class Command(BaseCommand):
    help = 'Apply the developer-reviewed Phase 3.0 structured applicability mappings to the 12 audited requirements.'

    @transaction.atomic
    def handle(self, *args, **options):
        rows = GrantRequirement.objects.filter(pk__in=OVERRIDES)
        if rows.count() != len(OVERRIDES):
            raise CommandError('phase30_applicability_requirements_missing')
        for row in rows:
            scope = dict(row.applicability or {})
            scope.pop('category', None)
            scope.update(OVERRIDES[row.id])
            row.applicability = scope
        GrantRequirement.objects.bulk_update(rows, ['applicability'])
        self.stdout.write(self.style.SUCCESS(f'phase30_rule_applicability_applied:{rows.count()}'))
