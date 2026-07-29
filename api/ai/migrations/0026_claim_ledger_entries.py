from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai', '0025_evidence_fact_structured_fields')]

    operations = [
        migrations.CreateModel(
            name='ClaimLedgerEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(blank=True, default='', max_length=512)), ('predicate', models.CharField(blank=True, default='', max_length=256)), ('object', models.TextField(blank=True, default='')),
                ('numeric_value', models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)), ('unit', models.CharField(blank=True, default='', max_length=64)), ('metric_definition', models.TextField(blank=True, default='')),
                ('time_range', models.JSONField(default=dict)), ('completion_status', models.CharField(blank=True, default='', max_length=32)), ('person_role', models.CharField(blank=True, default='', max_length=32)),
                ('funding_source', models.CharField(blank=True, default='', max_length=256)), ('amount', models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)), ('locked', models.BooleanField(default=False)),
                ('claim', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='ledger_entries', to='ai.claim')), ('evidence_fact', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='claim_ledger_entries', to='ai.evidencefact')), ('proposal_decision', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='claim_ledger_entries', to='ai.proposaldecision')),
            ],
        ),
    ]
