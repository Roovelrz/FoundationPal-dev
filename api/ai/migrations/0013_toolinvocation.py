from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ai', '0012_rag_evidence_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='ToolInvocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tool_name', models.CharField(db_index=True, max_length=64)),
                ('caller_role', models.CharField(max_length=32)),
                ('organization_id', models.CharField(blank=True, default='', max_length=64)),
                ('proposal_id', models.IntegerField(blank=True, null=True)),
                ('idempotency_key', models.CharField(blank=True, default='', max_length=128)),
                ('request_hash', models.CharField(blank=True, default='', max_length=64)),
                ('status', models.CharField(default='done', max_length=16)),
                ('result_json', models.JSONField(default=dict)),
                ('error_code', models.CharField(blank=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('caller', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('workflow_run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tool_invocations', to='ai.workflowrun')),
            ],
        ),
        migrations.AddConstraint(
            model_name='toolinvocation',
            constraint=models.UniqueConstraint(fields=('tool_name', 'caller_role', 'caller', 'organization_id', 'idempotency_key'), name='toolinvocation_idempotency_unique'),
        ),
        migrations.AddIndex(
            model_name='toolinvocation',
            index=models.Index(fields=['organization_id', 'tool_name', 'created_at'], name='ai_toolinvo_organiz_ebf6ea_idx'),
        ),
    ]
