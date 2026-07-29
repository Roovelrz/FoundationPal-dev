import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


IDENTITY_FIELDS = {"reviewer", "signed_by"}


def replace_identity(value, reviewer):
    changed = 0
    if isinstance(value, dict):
        for key, child in value.items():
            if key in IDENTITY_FIELDS and isinstance(child, str) and child != reviewer:
                value[key] = reviewer
                changed += 1
            else:
                changed += replace_identity(child, reviewer)
    elif isinstance(value, list):
        for child in value:
            changed += replace_identity(child, reviewer)
    return changed


class Command(BaseCommand):
    help = "Replace Phase 3.0 administrative reviewer identity fields without altering review dates or evidence data."

    def add_arguments(self, parser):
        parser.add_argument("--directory", required=True)
        parser.add_argument("--reviewer", required=True)

    def handle(self, *args, **options):
        directory = Path(options["directory"])
        reviewer = options["reviewer"].strip()
        if not directory.is_dir():
            raise CommandError(f"Directory does not exist: {directory}")
        if not reviewer:
            raise CommandError("Reviewer must not be empty.")

        files_changed = 0
        fields_changed = 0
        for path in sorted(directory.rglob("*.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            changed = replace_identity(value, reviewer)
            if not changed:
                continue
            path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            files_changed += 1
            fields_changed += changed
            self.stdout.write(f"updated {path.relative_to(directory)}: {changed}")

        self.stdout.write(
            self.style.SUCCESS(
                f"reviewer={reviewer}; files_changed={files_changed}; fields_changed={fields_changed}"
            )
        )
