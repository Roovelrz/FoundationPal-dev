import json

from django.core.management.base import BaseCommand, CommandError

from ai.phase40_p1 import validate_holdout


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--mapping-kind-prefix', default='phase40_p0v5_')

    def handle(self, *args, **options):
        result = validate_holdout(options['input_dir'], options['mapping_kind_prefix'])
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        if not result['valid']:
            raise CommandError('phase40_p1_holdout_invalid')
