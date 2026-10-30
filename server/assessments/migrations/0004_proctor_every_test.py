from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def proctor_upcoming_tests(apps, schema_editor):
    """Every test is proctored: switch it on for tests nobody has started yet.
    Tests already started (or over) keep the rules their students sat under."""
    from ai import vision

    Assessment = apps.get_model("assessments", "Assessment")
    AssessmentAttempt = apps.get_model("assessments", "AssessmentAttempt")
    now = timezone.now()
    camera = vision.available()
    for test in Assessment.objects.filter(monitoring_enabled=False):
        if test.starts_at + timedelta(minutes=test.duration_minutes) <= now:
            continue
        if AssessmentAttempt.objects.filter(assessment_id=test.pk).exists():
            continue
        test.monitoring_enabled = True
        if not camera:
            test.camera_required = False
            test.phone_detection_enabled = False
        test.save(update_fields=["monitoring_enabled", "camera_required", "phone_detection_enabled"])


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0003_monitoring"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assessment",
            name="monitoring_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(proctor_upcoming_tests, migrations.RunPython.noop),
    ]
