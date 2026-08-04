from django.db import migrations, models


def assign_workspace_numbers(apps, schema_editor):
    Organization = apps.get_model('orgs', 'Organization')
    Proposal = apps.get_model('proposals', 'Proposal')
    db_alias = schema_editor.connection.alias

    for org in Organization.objects.using(db_alias).all().iterator():
        number = 1
        for proposal in Proposal.objects.using(db_alias).filter(org_id=org.pk).order_by('created_at', 'id').iterator():
            Proposal.objects.using(db_alias).filter(pk=proposal.pk).update(workspace_number=number)
            number += 1
        Organization.objects.using(db_alias).filter(pk=org.pk).update(next_proposal_number=number)


def unassign_workspace_numbers(apps, schema_editor):
    Proposal = apps.get_model('proposals', 'Proposal')
    Proposal.objects.using(schema_editor.connection.alias).update(workspace_number=None)


class Migration(migrations.Migration):
    dependencies = [
        ('orgs', '0006_organization_next_proposal_number'),
        ('proposals', '0009_proposal_final_markdown'),
    ]

    operations = [
        migrations.AddField(
            model_name='proposal',
            name='workspace_number',
            field=models.PositiveIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(assign_workspace_numbers, unassign_workspace_numbers),
        migrations.AddConstraint(
            model_name='proposal',
            constraint=models.UniqueConstraint(
                condition=models.Q(('workspace_number__isnull', False)),
                fields=('org', 'workspace_number'),
                name='proposal_org_workspace_number_unique',
            ),
        ),
    ]
