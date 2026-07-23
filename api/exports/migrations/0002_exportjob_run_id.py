from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('exports', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='exportjob',
            name='run_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
    ]
