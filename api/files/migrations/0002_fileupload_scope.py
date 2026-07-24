from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('files', '0001_initial'),
        ('orgs', '0001_initial'),
        ('proposals', '0009_proposal_final_markdown'),
    ]

    operations = [
        migrations.AddField(
            model_name='fileupload',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='uploads', to='orgs.organization'),
        ),
        migrations.AddField(
            model_name='fileupload',
            name='proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploads', to='proposals.proposal'),
        ),
        migrations.AddIndex(
            model_name='fileupload',
            index=models.Index(fields=['organization', 'proposal', 'created_at'], name='file_upload_orgprop_idx'),
        ),
    ]
