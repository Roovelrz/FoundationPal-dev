from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('orgs', '0005_orginvite_expires_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='next_proposal_number',
            field=models.PositiveIntegerField(default=1),
        ),
    ]
