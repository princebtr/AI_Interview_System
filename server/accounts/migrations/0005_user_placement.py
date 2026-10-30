"""Students store their cohort's section, department and batch too."""
import django.db.models.deletion
from django.db import migrations, models


def backfill_placement(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Cohort = apps.get_model("institutions", "Cohort")
    for cohort in Cohort.objects.select_related("section__department"):
        section = cohort.section
        User.objects.filter(cohort=cohort).update(
            section=section, department=section.department, batch_id=section.department.batch_id
        )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_token_version_login_throttle'),
        ('institutions', '0006_academic_structure'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='batch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='students', to='institutions.batch'),
        ),
        migrations.AddField(
            model_name='user',
            name='department',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='students', to='institutions.department'),
        ),
        migrations.AddField(
            model_name='user',
            name='section',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='students', to='institutions.section'),
        ),
        migrations.RunPython(backfill_placement, migrations.RunPython.noop),
    ]
