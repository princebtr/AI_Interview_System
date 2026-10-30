"""Proctoring shared by every kind of test: scheduled tests (assessments app)
and practice tests (this app). The AI interview has its own lighter checks.

The browser detects (full-screen exits, sustained speech, camera checks) and
reports each confirmed event with its own id; the server is authoritative:
- (target, event_id) is unique, so retries and duplicates never count twice;
- counters change with atomic conditional updates that only apply while the
  test is open, so nothing lands after submission;
- reaching a limit submits through the caller's `submit`, which must finalise
  exactly once and set `target.graded_now`.

A "target" is the record being proctored (an AssessmentAttempt or a
PracticeQuiz). Both carry the same counter, status and frame fields.
"""
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import F, Q
from django.utils import timezone

from config.http import BadRequest

from . import detection, services, vision
from .models import PracticeAttempt, PracticeQuiz, PracticeViolation

logger = logging.getLogger(__name__)

# violation type -> (counter field, submission reason when its limit is reached)
COUNTED = {
    "screen_switch": ("screen_switch_count", "SCREEN_SWITCH_LIMIT"),
    "voice": ("voice_violation_count", "VOICE_VIOLATION_LIMIT"),
    "face": ("face_violation_count", "FACE_VIOLATION_LIMIT"),
    "phone": ("phone_violation_count", "PHONE_DETECTION_LIMIT"),
}

DETAILS = {
    "screen_switch": {"fullscreen_exit", "tab_hidden", "left_page"},
    "voice": {"sustained_speech"},
    # camera_unavailable: the camera stayed off past the grace period.
    "face": {"no_face", "multiple_faces", "camera_unavailable"},
    "phone": {"phone_detected"},
    # Logged for the timeline; never counted or penalised.
    "technical": {
        "camera_interrupted",
        "microphone_interrupted",
        "camera_checks_failing",
        "monitoring_resumed",
        "page_reloaded",
    },
}
DEGRADED = {"camera_interrupted", "microphone_interrupted", "camera_checks_failing"}

# Which rule (in the API's rules object) turns each check on.
ENABLED_BY = {
    "screen_switch": "fullscreenRequired",
    "voice": "microphoneRequired",
    "face": "cameraRequired",
    "phone": "phoneDetection",
}

# The platform's default limits: new scheduled tests start from these, and
# practice tests always use them.
DEFAULT_LIMITS = {"screen_switch": 3, "voice": 5, "face": 5, "phone": 3}
DEFAULT_FACE_PENALTY = 5

EVENT_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

STUDENT_SUBMITTED = "STUDENT_SUBMITTED"


def min_frame_interval():
    """At most one camera check per test (or interview) this often."""
    return timedelta(milliseconds=settings.PROCTORING["MIN_SERVER_INTERVAL_MS"])


def detection_config():
    """How often the browser sends frames and how much evidence makes an incident."""
    return detection.client_config(settings.PROCTORING)


def capabilities():
    camera = vision.available()
    return {"cameraChecks": camera, "phoneDetection": camera, "speechDetection": True}


def counts_of(target):
    return {kind: getattr(target, field) for kind, (field, _) in COUNTED.items()}


def validate_event(rules, *, event_id, kind, detail, confidence):
    """Reject malformed reports and checks this test doesn't run."""
    if not isinstance(event_id, str) or not EVENT_ID.match(event_id):
        raise BadRequest("eventId must be 8-64 letters, digits, '-' or '_'")
    if not isinstance(kind, str) or not isinstance(detail, str) or kind not in DETAILS or detail not in DETAILS[kind]:
        raise BadRequest("Unknown violation type")
    if kind != "technical" and not rules.get(ENABLED_BY[kind]):
        raise BadRequest("This test doesn't check that")
    if confidence is not None and (
        isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1
    ):
        raise BadRequest("confidence must be a number from 0 to 1")


def record_event(target, events, fk, *, rules, event_id, kind, detail, confidence=None, penalty=0.0, prepare=None, submit, closed_message):
    """Record one confirmed event for `target`. Returns (event, created).

    - `events`/`fk`: the event model and the name of its foreign key to the target
    - `prepare()`: runs before a new event is stored (e.g. saving the latest
      answers); it may raise to refuse the report (time is up)
    - `submit(reason)`: finalises the target when a limit is reached
    """
    validate_event(rules, event_id=event_id, kind=kind, detail=detail, confidence=confidence)
    model = type(target)

    existing = events.objects.filter(**{fk: target}, event_id=event_id).first()
    if existing:
        return existing, False
    if target.submitted_at is not None:
        raise BadRequest(closed_message)
    if prepare:
        prepare()

    try:
        event = events.objects.create(
            **{fk: target},
            event_id=event_id,
            violation_type=kind,
            detail=detail,
            confidence=None if confidence is None else round(float(confidence), 3),
            action_taken="logged",
        )
    except IntegrityError:  # the same report arrived twice at once
        return events.objects.get(**{fk: target}, event_id=event_id), False

    if kind == "technical":
        status = "degraded" if detail in DEGRADED else "active"
        model.objects.filter(pk=target.pk, submitted_at=None).update(monitoring_status=status)
        target.monitoring_status = status
        return event, True

    count_field, reason = COUNTED[kind]
    updates = {count_field: F(count_field) + 1}
    if penalty:
        updates["total_penalty"] = F("total_penalty") + penalty
    applied = model.objects.filter(pk=target.pk, submitted_at=None).update(**updates)
    if not applied:  # submitted by a concurrent request in the meantime
        events.objects.filter(pk=event.pk).update(action_taken="ignored")
        event.action_taken = "ignored"
        target.refresh_from_db()
        return event, True

    target.refresh_from_db(fields=[count_field] + (["total_penalty"] if penalty else []))
    count = getattr(target, count_field)
    limit = rules["limits"].get(kind, 0)
    action = "penalised" if penalty else "warned"
    if limit and count >= limit:
        submit(reason)
        if getattr(target, "graded_now", False):
            action = "auto_submitted"
    events.objects.filter(pk=event.pk).update(action_taken=action, penalty_applied=penalty, count_after=count)
    event.action_taken, event.penalty_applied, event.count_after = action, penalty, count
    return event, True


class FrameRefused(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.message, self.status = message, status


def camera_check(target, upload, *, phone=True):
    """Run the camera checks on one webcam frame for an open `target`.
    Nothing is stored. At most one check per min_frame_interval()."""
    if not vision.available():
        raise FrameRefused("Camera checks aren't available right now", 503)
    frame, _ = vision.read_image(upload)

    now = timezone.now()
    recent = now - min_frame_interval()
    claimed = type(target).objects.filter(
        Q(last_frame_at=None) | Q(last_frame_at__lte=recent), pk=target.pk, submitted_at=None
    ).update(last_frame_at=now, frames_analysed=F("frames_analysed") + 1, monitoring_status="active")
    if not claimed:
        raise FrameRefused("Camera checks are arriving too quickly", 429)

    try:
        result = vision.analyse(frame)
    except Exception:  # model failed to load or run: never the student's fault
        logger.exception("Camera check failed")
        raise FrameRefused("Camera checks aren't available right now", 503)
    if not phone:
        result.update(phone=False, phoneSuspected=False, phoneConfidence=0.0, phoneBoxes=[])
    return result


def interview_camera_check(user, upload):
    """Camera checks for AI interview practice (no attempt row to rate-limit on,
    so the cache holds the last check per student). Nothing is stored."""
    if not vision.available():
        raise FrameRefused("Camera checks aren't available right now", 503)
    frame, _ = vision.read_image(upload)
    seconds = max(1, round(min_frame_interval().total_seconds()))
    if not cache.add(f"proctor-frame:{user.pk}", True, timeout=seconds):
        raise FrameRefused("Camera checks are arriving too quickly", 429)
    try:
        return vision.analyse(frame)
    except Exception:
        logger.exception("Camera check failed")
        raise FrameRefused("Camera checks aren't available right now", 503)


# --------------------------------------------------------------------------- #
# Practice tests                                                              #
# --------------------------------------------------------------------------- #

PRACTICE_CLOSED = "This practice test was already submitted."


def practice_rules(quiz):
    """Practice tests use a default scheduled test's rules, without mark
    penalties (practice is scored as a percentage)."""
    camera = quiz.camera_checks
    return {
        "enabled": quiz.proctored,
        "fullscreenRequired": True,
        "cameraRequired": camera,
        "microphoneRequired": True,
        "phoneDetection": camera,
        "limits": dict(DEFAULT_LIMITS),
        "facePenalty": 0,
        "detection": detection_config(),
    }


def practice_state(quiz):
    return {**practice_rules(quiz), "counts": counts_of(quiz), "totalPenalty": 0}


def clean_practice_answers(quiz, answers):
    """{question id: "A"-"D"} for this quiz's questions; anything else is dropped."""
    if answers is None:
        return {}
    if not isinstance(answers, dict):
        raise BadRequest("Answers must be an object of question id to A, B, C or D")
    ids = {str(q["id"]) for q in quiz.questions}
    cleaned = {}
    for qid, letter in answers.items():
        letter = letter.strip().upper() if isinstance(letter, str) else ""
        if str(qid) in ids and letter in ("A", "B", "C", "D"):
            cleaned[str(qid)] = letter
    return cleaned


def submit_practice(quiz, answers, reason):
    """Grade and record a practice test exactly once. Sets `quiz.graded_now`."""
    cleaned = clean_practice_answers(quiz, answers)
    claimed = PracticeQuiz.objects.filter(pk=quiz.pk, submitted_at=None).update(
        submitted_at=timezone.now(), submission_reason=reason, answers=cleaned
    )
    quiz.graded_now = bool(claimed)
    if claimed:
        result = services.grade_mcq(quiz.questions, cleaned)
        PracticeAttempt.objects.create(
            institution_id=quiz.institution_id,
            user_id=quiz.user_id,
            kind="mcq",
            subject=quiz.subject,
            subject_key=PracticeAttempt.key_for(quiz.subject),
            score=result["percentage"],
            correct=result["score"],
            total=result["totalQuestions"],
        )
    quiz.refresh_from_db()
    return quiz


def practice_result(quiz):
    """A submitted practice test's graded result with its proctoring summary."""
    return {
        **services.grade_mcq(quiz.questions, quiz.answers or {}),
        "submissionReason": quiz.submission_reason or STUDENT_SUBMITTED,
        "monitoring": practice_state(quiz),
    }


def record_practice_violation(quiz, *, event_id, kind, detail, confidence=None, answers=None):
    if not quiz.proctored:
        raise BadRequest("This practice test isn't proctored")
    # Validate the answers before anything is stored; they are graded if this
    # report reaches a limit.
    clean_practice_answers(quiz, answers)
    return record_event(
        quiz,
        PracticeViolation,
        "quiz",
        rules=practice_rules(quiz),
        event_id=event_id,
        kind=kind,
        detail=detail,
        confidence=confidence,
        submit=lambda reason: submit_practice(quiz, answers, reason),
        closed_message=PRACTICE_CLOSED,
    )


def practice_camera_check(quiz, upload):
    if not (quiz.proctored and quiz.camera_checks):
        raise FrameRefused("This practice test doesn't use camera checks", 400)
    if quiz.submitted_at is not None:
        raise FrameRefused(PRACTICE_CLOSED, 400)
    return camera_check(quiz, upload)
