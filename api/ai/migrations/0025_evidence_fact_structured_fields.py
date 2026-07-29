from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai', '0024_claim_ledger')]

    operations = [
        migrations.AddField(model_name='evidencefact', name='authority_level', field=models.CharField(blank=True, default='', max_length=32)),
        migrations.AddField(model_name='evidencefact', name='author_order', field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name='evidencefact', name='metric_definition', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='evidencefact', name='project_status', field=models.CharField(blank=True, default='', max_length=32)),
        migrations.AddField(model_name='evidencefact', name='unit', field=models.CharField(blank=True, default='', max_length=64)),
    ]
