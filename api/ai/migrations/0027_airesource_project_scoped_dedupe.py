from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ai', '0026_claim_ledger_entries'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='airesource',
            name='airesource_org_sha_parser_unique',
        ),
        migrations.AddConstraint(
            model_name='airesource',
            constraint=models.UniqueConstraint(
                fields=('organization_id', 'proposal_id', 'sha256', 'parser_version'),
                name='airesource_org_proposal_sha_parser_unique',
            ),
        ),
    ]
