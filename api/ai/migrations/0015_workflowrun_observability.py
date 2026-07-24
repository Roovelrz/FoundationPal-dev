from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai', '0014_humanapprovaltask')]

    operations = [
        migrations.AddField(model_name='workflowrun', name='architecture', field=models.CharField(default='sequential', max_length=32)),
        migrations.AddField(model_name='workflowrun', name='status', field=models.CharField(default='running', max_length=32)),
        migrations.AddField(model_name='workflowrun', name='trace_json', field=models.JSONField(default=list)),
        migrations.AddField(model_name='workflowrun', name='handoffs_json', field=models.JSONField(default=list)),
        migrations.AddField(model_name='workflowrun', name='revision_count', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='workflowrun', name='fallback_mode', field=models.CharField(blank=True, default='', max_length=32)),
        migrations.AddField(model_name='workflowrun', name='resumed_from_checkpoint', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='workflowrun', name='completed_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='toolinvocation', name='duration_ms', field=models.IntegerField(default=0)),
        migrations.AddField(model_name='toolinvocation', name='replay_count', field=models.PositiveIntegerField(default=0)),
    ]
