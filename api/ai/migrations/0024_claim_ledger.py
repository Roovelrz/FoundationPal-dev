from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai', '0023_phase11_seed_map')]

    operations = [
        migrations.AddField(
            model_name='claim',
            name='ledger',
            field=models.JSONField(default=dict),
        ),
    ]
