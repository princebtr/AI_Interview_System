"""Proctoring for scheduled tests: settings, violation events, penalties,
automatic submission and review. Every new scheduled test is proctored;
educators choose which checks run and their limits.

The shared rules (once-only events, counting only while open, submitting once
at a limit) live in ai/proctoring.py and also serve practice tests.

Score: raw_score comes from the answers; score = max(0, raw_score - total_penalty).
Only face violations carry a penalty. The test engine has no partial marks or
negative marking, and educators adjust a result only by reviewing its
violations: dismissing a penalised one refunds its penalty.
"""
from django.utils import timezone

from ai import proctoring, vision
from ai.proctoring import FrameRefused, capabilities  # noqa: F401  (re-exported for the views)
from config.http import BadRequest

from . import sitting
from .models import AssessmentAttempt, ViolationEvent

LIMITS = proctoring.DEFAULT_LIMITS

# Form key -> (model field, default). There is no "off" switch: every test is proctored.
SWITCHES = {
    "fullscreenRequired": ("fullscreen_required", True),
    "cameraRequired": ("camera_required", True),
    "microphoneRequired": ("microphone_required", True),
    "phoneDetection": ("phone_detection_enabled", True),
}
# Form key -> (model field, default, low, high, label). A limit of 0 means "warn only".
NUMBERS = {
    "maxScreenSwitches": ("max_screen_switches", LIMITS["screen_switch"], 0, 20, "Full-screen exits allowed"),
    "maxVoiceViolations": ("max_voice_violations", LIMITS["voice"], 0, 50, "Speech detections allowed"),
    "maxFaceViolations": ("max_face_violations", LIMITS["face"], 0, 50, "Camera violations allowed"),
    "facePenalty": ("face_violation_penalty", proctoring.DEFAULT_FACE_PENALTY, 0, 100, "Marks deducted per camera violation"),
    "maxPhoneViolations": ("max_phone_violations", LIMITS["phone"], 0, 20, "Phone detections allowed"),
}


def clean_config(data, errors):
    """Validate the `monitoring` (proctoring) object of the create/edit form into
    model fields. Omitted keys, or the whole object, take the defaults; camera
    checks default to on only where the server can run them."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        errors.append({"field": "monitoring", "message": "monitoring must be an object"})
        return {}
    if data.get("enabled", True) is not True:
        errors.append({"field": "monitoring.enabled", "message": "Every test is proctored; proctoring can't be turned off"})
        return {}

    camera_available = vision.available()
    fields = {"monitoring_enabled": True}
    for key, (field, default) in SWITCHES.items():
        if key == "cameraRequired" and key not in data:
            default = camera_available
        value = data.get(key, default)
        if not isinstance(value, bool):
            errors.append({"field": f"monitoring.{key}", "message": f"{key} must be true or false"})
            continue
        fields[field] = value
    for key, (field, default, low, high, label) in NUMBERS.items():
        value = data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            errors.append({"field": f"monitoring.{key}", "message": f"{label} must be a whole number from {low} to {high}"})
            continue
        fields[field] = value

    if not any(fields.get(f) for f in ("fullscreen_required", "camera_required", "microphone_required")):
        errors.append({"field": "monitoring", "message": "Turn on at least one proctoring check"})
    if fields.get("camera_required") and not camera_available:
        errors.append({"field": "monitoring.cameraRequired", "message": "Camera checks aren't available on this server"})
    if not fields.get("camera_required", True):
        fields["phone_detection_enabled"] = False
    return fields


def record_violation(attempt, *, event_id, kind, detail, confidence=None, answers=None, review=None):
    """Record one confirmed event. Returns (event, created). Reaching a limit
    submits the attempt with the matching reason."""
    assessment = attempt.assessment
    if not assessment.monitoring_enabled:
        raise BadRequest("This test isn't proctored")

    def prepare():
        # Save the latest answers first, so an automatic submission grades them.
        # (save_answers refuses, and finalises, once time is up.)
        if answers is not None:
            sitting.save_answers(attempt, answers, review)
        elif timezone.now() >= assessment.ends_at:
            sitting.finalize_if_expired(attempt)
            raise BadRequest("Time is up. Your saved answers were submitted.")

    return proctoring.record_event(
        attempt,
        ViolationEvent,
        "attempt",
        rules=assessment.monitoring_config(),
        event_id=event_id,
        kind=kind,
        detail=detail,
        confidence=confidence,
        penalty=float(assessment.face_violation_penalty) if kind == "face" else 0.0,
        prepare=prepare,
        submit=lambda reason: sitting.grade(attempt, auto=True, reason=reason),
        closed_message="This test was already submitted",
    )


def analyse_frame(attempt, upload):
    """Run the camera checks on one webcam frame. Nothing is stored."""
    assessment = attempt.assessment
    if not (assessment.monitoring_enabled and assessment.camera_required):
        raise FrameRefused("This test doesn't use camera checks", 400)
    if attempt.submitted_at is not None:
        raise FrameRefused("This test was already submitted", 400)
    now = timezone.now()
    if now >= assessment.ends_at:
        sitting.finalize_if_expired(attempt, now)
        raise FrameRefused("Time is up. Your saved answers were submitted.", 400)
    return proctoring.camera_check(attempt, upload, phone=assessment.phone_detection_enabled)


def review_violation(event, status, reviewer):
    """An educator upholds or dismisses a violation after the attempt is
    submitted. Penalties of dismissed events are refunded."""
    if status not in ("upheld", "dismissed", "unreviewed"):
        raise BadRequest("reviewStatus must be upheld, dismissed or unreviewed")
    if event.violation_type == "technical":
        raise BadRequest("Technical events aren't violations")
    attempt = event.attempt
    if attempt.submitted_at is None:
        raise BadRequest("Review violations once the student has submitted")

    event.review_status = status
    event.reviewed_by = reviewer if status != "unreviewed" else None
    event.reviewed_at = timezone.now() if status != "unreviewed" else None
    event.save(update_fields=["review_status", "reviewed_by", "reviewed_at"])

    total = sum(
        e.penalty_applied
        for e in ViolationEvent.objects.filter(attempt=attempt).exclude(review_status="dismissed")
    )
    raw = attempt.raw_score if attempt.raw_score is not None else attempt.final_score or 0
    score = max(0.0, raw - total)
    AssessmentAttempt.objects.filter(pk=attempt.pk).update(total_penalty=total, score=score)
    attempt.total_penalty, attempt.score = total, score
    return event
