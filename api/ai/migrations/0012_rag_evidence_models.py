import hashlib

from django.db import migrations, models
import django.db.models.deletion


def populate_chunk_trace_fields(apps, schema_editor):
    AIChunk = apps.get_model('ai', 'AIChunk')
    for chunk in AIChunk.objects.select_related('resource').all().iterator():
        normalized = ' '.join((chunk.text or '').split())
        text_sha = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
        stable = hashlib.sha256(
            f'{chunk.resource.sha256}:pdfminer-v1:{chunk.chunk_index}:{text_sha}'.encode('utf-8')
        ).hexdigest()
        chunk.normalized_text = normalized
        chunk.text_sha256 = text_sha
        chunk.stable_chunk_id = stable
        chunk.page_start = 1
        chunk.page_end = 1
        chunk.token_count = max(1, len((chunk.text or '').split()))
        chunk.save(update_fields=['normalized_text', 'text_sha256', 'stable_chunk_id', 'page_start', 'page_end', 'token_count'])


class Migration(migrations.Migration):
    dependencies = [('ai', '0011_alter_aimetric_type'), ('proposals', '0009_proposal_final_markdown')]

    operations = [
        migrations.RemoveIndex(model_name='airesource', name='ai_airesour_type_4368d5_idx'),
        migrations.RemoveConstraint(model_name='aichunk', name='aichunk_resource_ord_unique'),
        migrations.RenameField(model_name='airesource', old_name='type', new_name='source_type'),
        migrations.AlterField(model_name='airesource', name='source_type', field=models.CharField(choices=[('guideline', 'guideline'), ('call_snapshot', 'call_snapshot'), ('successful_case', 'successful_case'), ('team_profile', 'team_profile'), ('template', 'template'), ('review_criteria', 'review_criteria'), ('sample', 'sample')], max_length=32)),
        migrations.AddField(model_name='airesource', name='organization_id', field=models.CharField(db_index=True, default='', max_length=64)),
        migrations.AddField(model_name='airesource', name='proposal_id', field=models.IntegerField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='airesource', name='evidence_purpose', field=models.CharField(choices=[('constraint', 'constraint'), ('fact', 'fact'), ('style', 'style'), ('template', 'template')], default='fact', max_length=16)),
        migrations.AddField(model_name='airesource', name='original_filename', field=models.CharField(blank=True, default='', max_length=512)),
        migrations.AddField(model_name='airesource', name='display_name', field=models.CharField(blank=True, default='', max_length=256)),
        migrations.AddField(model_name='airesource', name='mime_type', field=models.CharField(blank=True, default='', max_length=128)),
        migrations.AddField(model_name='airesource', name='parser_version', field=models.CharField(default='pdfminer-v1', max_length=64)),
        migrations.AddField(model_name='airesource', name='embedding_model', field=models.CharField(blank=True, default='', max_length=128)),
        migrations.AddField(model_name='airesource', name='embedding_revision', field=models.CharField(blank=True, default='', max_length=128)),
        migrations.AddField(model_name='airesource', name='embedding_dimension', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='airesource', name='page_count', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='airesource', name='status', field=models.CharField(choices=[('ready', 'ready'), ('error', 'error'), ('deleted', 'deleted')], default='ready', max_length=16)),
        migrations.AddField(model_name='airesource', name='error_code', field=models.CharField(blank=True, default='', max_length=64)),
        migrations.AddField(model_name='airesource', name='is_deleted', field=models.BooleanField(db_index=True, default=False)),
        migrations.RenameField(model_name='aichunk', old_name='ord', new_name='chunk_index'),
        migrations.RenameField(model_name='aichunk', old_name='token_len', new_name='token_count'),
        migrations.AddField(model_name='aichunk', name='stable_chunk_id', field=models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField(model_name='aichunk', name='normalized_text', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='aichunk', name='text_sha256', field=models.CharField(blank=True, db_index=True, default='', max_length=64)),
        migrations.AddField(model_name='aichunk', name='page_start', field=models.PositiveIntegerField(default=1)),
        migrations.AddField(model_name='aichunk', name='page_end', field=models.PositiveIntegerField(default=1)),
        migrations.AddField(model_name='aichunk', name='section_title', field=models.CharField(blank=True, default='', max_length=512)),
        migrations.AddField(model_name='aichunk', name='heading_path', field=models.JSONField(default=list)),
        migrations.AddField(model_name='aichunk', name='embedding_model', field=models.CharField(blank=True, default='', max_length=128)),
        migrations.AddField(model_name='aichunk', name='embedding_dimension', field=models.PositiveIntegerField(default=0)),
        migrations.RunPython(populate_chunk_trace_fields, migrations.RunPython.noop),
        migrations.AlterField(model_name='aichunk', name='stable_chunk_id', field=models.CharField(db_index=True, max_length=64)),
        migrations.AlterField(model_name='aichunk', name='text_sha256', field=models.CharField(db_index=True, default='', max_length=64)),
        migrations.AddConstraint(model_name='aichunk', constraint=models.UniqueConstraint(fields=('resource', 'chunk_index'), name='aichunk_resource_index_unique')),
        migrations.AddConstraint(model_name='airesource', constraint=models.UniqueConstraint(fields=('organization_id', 'sha256', 'parser_version'), name='airesource_org_sha_parser_unique')),
        migrations.AddIndex(model_name='airesource', index=models.Index(fields=['organization_id', 'proposal_id', 'source_type'], name='ai_airesour_orgpsrc_idx')),
        migrations.CreateModel(
            name='EvidenceUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('planner', 'planner'), ('writer', 'writer'), ('reviser', 'reviser'), ('formatter', 'formatter')], max_length=16)),
                ('retrieval_query', models.TextField(blank=True, default='')),
                ('rank', models.PositiveIntegerField(default=0)), ('similarity_score', models.FloatField(default=0.0)),
                ('used_in_prompt', models.BooleanField(default=False)), ('cited_by_model', models.BooleanField(default=False)),
                ('evidence_alias', models.CharField(blank=True, default='', max_length=32)), ('snapshot_text', models.TextField()),
                ('document_name_snapshot', models.CharField(blank=True, default='', max_length=256)),
                ('page_start_snapshot', models.PositiveIntegerField(default=1)), ('page_end_snapshot', models.PositiveIntegerField(default=1)),
                ('section_title_snapshot', models.CharField(blank=True, default='', max_length=512)), ('prompt_version', models.PositiveIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ai_job', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='evidence_usages', to='ai.aijob')),
                ('chunk', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='evidence_usages', to='ai.aichunk')),
                ('proposal_section', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='evidence_usages', to='proposals.proposalsection')),
                ('workflow_run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='evidence_usages', to='ai.workflowrun')),
            ],
        ),
        migrations.AddConstraint(model_name='evidenceusage', constraint=models.UniqueConstraint(fields=('ai_job', 'chunk', 'role'), name='evidenceusage_job_chunk_role_unique')),
        migrations.AddIndex(model_name='evidenceusage', index=models.Index(fields=['proposal_section', 'created_at'], name='ai_evidence_propcrt_idx')),
    ]
