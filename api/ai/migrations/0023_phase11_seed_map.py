from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai', '0022_phase9_reviewing')]

    operations = [
        migrations.CreateModel(
            name='Phase11SeedMap',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(max_length=32)),
                ('external_id', models.CharField(max_length=160)),
                ('target_id', models.PositiveIntegerField()),
                ('source_sha256', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'constraints': [models.UniqueConstraint(fields=('kind', 'external_id'), name='phase11seedmap_kind_external_unique')]},
        ),
    ]
