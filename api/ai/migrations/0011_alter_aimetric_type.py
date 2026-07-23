from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai', '0010_workflowrun_run_ids')]

    operations = [
        migrations.AlterField(
            model_name='aimetric',
            name='type',
            field=models.CharField(
                choices=[
                    ('plan', 'plan'),
                    ('write', 'write'),
                    ('revise', 'revise'),
                    ('format', 'format'),
                    ('promote', 'promote'),
                    ('export', 'export'),
                ],
                max_length=16,
            ),
        ),
    ]
