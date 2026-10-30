"""Batch -> Department -> Section -> Cohort.

Cohorts used to hang directly off the institution. Each institution that has
cohorts gets one batch (named after its academic year), with a "General"
department and section holding every existing cohort; admins can rename these
and build out the real structure in the app.
"""
import django.db.models.deletion
import django_mongodb_backend.fields
from django.db import migrations, models

DEFAULT_GROUP = "General"


def node_fields(related_name, parent=None):
    fields = [
        ('id', django_mongodb_backend.fields.ObjectIdAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('name', models.CharField(max_length=60)),
        ('name_key', models.CharField(editable=False, max_length=60)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('institution', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name=related_name, to='institutions.institution')),
    ]
    if parent:
        fields.append((parent, models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name=related_name, to=f'institutions.{parent}')))
    return fields


def key_for(name):
    return " ".join(name.split()).casefold()


def place_existing_cohorts(apps, schema_editor):
    Institution = apps.get_model("institutions", "Institution")
    Batch = apps.get_model("institutions", "Batch")
    Department = apps.get_model("institutions", "Department")
    Section = apps.get_model("institutions", "Section")
    Cohort = apps.get_model("institutions", "Cohort")

    for institution in Institution.objects.filter(pk__in=Cohort.objects.values_list("institution_id", flat=True)):
        batch_name = " ".join((institution.academic_year or "").split()) or "Current batch"
        batch, _ = Batch.objects.get_or_create(
            institution=institution, name_key=key_for(batch_name), defaults={"name": batch_name}
        )
        department, _ = Department.objects.get_or_create(
            institution=institution, batch=batch, name_key=key_for(DEFAULT_GROUP), defaults={"name": DEFAULT_GROUP}
        )
        section, _ = Section.objects.get_or_create(
            institution=institution, department=department, name_key=key_for(DEFAULT_GROUP), defaults={"name": DEFAULT_GROUP}
        )
        Cohort.objects.filter(institution=institution, section=None).update(section=section)


class Migration(migrations.Migration):

    dependencies = [
        ('institutions', '0005_institution_primary_color_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Batch',
            fields=node_fields('batches'),
            options={
                'ordering': ['name_key'],
                'abstract': False,
                'constraints': [models.UniqueConstraint(fields=('institution', 'name_key'), name='unique_batch_per_institution')],
            },
        ),
        migrations.CreateModel(
            name='Department',
            fields=node_fields('departments', 'batch'),
            options={
                'ordering': ['name_key'],
                'abstract': False,
                'constraints': [models.UniqueConstraint(fields=('batch', 'name_key'), name='unique_department_per_batch')],
            },
        ),
        migrations.CreateModel(
            name='Section',
            fields=node_fields('sections', 'department'),
            options={
                'ordering': ['name_key'],
                'abstract': False,
                'constraints': [models.UniqueConstraint(fields=('department', 'name_key'), name='unique_section_per_department')],
            },
        ),
        migrations.RemoveConstraint(
            model_name='cohort',
            name='unique_cohort_per_institution',
        ),
        migrations.AddField(
            model_name='cohort',
            name='section',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cohorts', to='institutions.section'),
        ),
        migrations.RunPython(place_existing_cohorts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='cohort',
            name='section',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cohorts', to='institutions.section'),
        ),
        migrations.AddConstraint(
            model_name='cohort',
            constraint=models.UniqueConstraint(fields=('section', 'name_key'), name='unique_cohort_per_section'),
        ),
    ]
