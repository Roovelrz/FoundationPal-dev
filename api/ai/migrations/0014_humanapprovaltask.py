from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('ai', '0013_toolinvocation')]

    operations = [
        migrations.CreateModel(
            name='HumanApprovalTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('proposal_id', models.IntegerField(db_index=True)),
                ('thread_id', models.CharField(max_length=128, unique=True)),
                ('node', models.CharField(max_length=64)),
                ('status', models.CharField(choices=[('pending', 'pending'), ('approved', 'approved'), ('ready_after_edit', 'ready_after_edit'), ('rejected', 'rejected')], default='pending', max_length=32)),
                ('input_json', models.JSONField(default=dict)),
                ('model_output_json', models.JSONField(default=dict)),
                ('decision_json', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('workflow_run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='human_tasks', to='ai.workflowrun')),
            ],
        ),
    ]
