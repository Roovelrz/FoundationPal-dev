import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai', '0009_aijobcontext_redaction_map_and_more')]

    operations = [
        migrations.CreateModel(
            name='WorkflowRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('run_id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('proposal_id', models.IntegerField(blank=True, null=True)),
                ('org_id', models.CharField(blank=True, default='', max_length=64)),
                ('provider', models.CharField(blank=True, default='', max_length=64)),
                ('schema_version', models.CharField(default='v1', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddField(model_name='aijob', name='run_id', field=models.UUIDField(db_index=True, default=uuid.uuid4)),
        migrations.AddField(model_name='aimetric', name='run_id', field=models.UUIDField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='aijobcontext', name='run_id', field=models.UUIDField(blank=True, db_index=True, null=True)),
    ]
