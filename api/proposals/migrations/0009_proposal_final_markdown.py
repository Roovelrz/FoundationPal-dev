from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('proposals', '0008_proposal_call_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='proposal',
            name='final_markdown',
            field=models.TextField(blank=True, default=''),
        ),
    ]
