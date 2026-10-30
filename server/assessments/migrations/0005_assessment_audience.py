"""Tests can be assigned to a batch, department, section or cohort. Existing
tests keep their cohort and gain its ancestors."""
import django.db.models.deletion
from django.db import migrations, models


def backfill_audience(apps, schema_editor):
    Assessment = apps.get_model("assessments", "Assessment")
    Cohort = apps.get_model("institutions", "Cohort")
    for cohort in Cohort.objects.select_related("section__department"):
        section = cohort.section
        Assessment.objects.filter(cohort=cohort).update(
            section=section, department=section.department, batch_id=section.department.batch_id
        )


class Migration(migrations.Migration):

    dependencies = [
        ('assessments', '0004_proctor_every_test'),
        ('institutions', '0006_academic_structure'),
    ]

    operations = [
        migrations.AddField(
            model_name='assessment',
            name='batch',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='assessments', to='institutions.batch'),
        ),
        migrations.AddField(
            model_name='assessment',
            name='department',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='assessments', to='institutions.department'),
        ),
        migrations.AddField(
            model_name='assessment',
            name='section',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='assessments', to='institutions.section'),
        ),
        migrations.AlterField(
            model_name='assessment',
            name='cohort',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='assessments', to='institutions.cohort'),
        ),
        migrations.RunPython(backfill_audience, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='assessment',
            name='batch',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assessments', to='institutions.batch'),
        ),
    ]
