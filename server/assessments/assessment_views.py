"""Scheduled tests: educators create and review them, students sit them.

Everything is scoped to the caller's institution. A test is assigned to a batch,
department, section or cohort; students only ever see tests assigned to a group
they belong to.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from accounts import validators as v
from accounts.auth import jwt_required, role_required
from accounts.models import User
from config.http import BadRequest, api_view, error, json_body
from institutions import structure
from institutions.models import AuditLog

from . import monitoring, sitting
from .models import Assessment, AssessmentAttempt, Question, ViolationEvent

STAFF = ("admin", "educator")
MAX_QUESTIONS = 100


def _int(data, key, low, high, label, errors):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        errors.append({"field": key, "message": f"{label} must be a whole number from {low} to {high}"})
        return None
    return value


def _text(data, key, limit, errors, label, required=False, min_len=0):
    value = data.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        errors.append({"field": key, "message": f"{label} must be text"})
        return ""
    value = " ".join(value.split()) if key in ("title", "subject") else value.strip()
    if required and len(value) < max(1, min_len):
        errors.append({"field": key, "message": f"{label} must be at least {max(1, min_len)} characters"})
    elif len(value) > limit:
        errors.append({"field": key, "message": f"{label} can be at most {limit} characters"})
    return value


def _find(model, pk, **scope):
    try:
        return model.objects.filter(pk=pk, **scope).first()
    except ValidationError:  # not a valid ObjectId
        return None


def _percentage(attempt, assessment):
    final = attempt.final_score
    if final is None or not assessment.total_marks:
        return None
    return round(final / assessment.total_marks * 100, 1)


# --------------------------------------------------------------------------- #
# Staff                                                                       #
# --------------------------------------------------------------------------- #


def _staff_queryset(request):
    tests = Assessment.objects.filter(institution=request.user.institution).select_related(
        *Assessment.AUDIENCE_FIELDS, "created_by"
    )
    if request.user.role != "admin":
        tests = tests.filter(created_by=request.user)
    return tests


def list_assessments(request):
    tests = list(_staff_queryset(request).order_by("-starts_at"))
    sitting.finalize_closed(tests)
    group_sizes = structure.student_counts(request.user.institution)

    stats = {t.pk: {"submitted": 0, "inProgress": 0, "_pct": []} for t in tests}
    by_id = {t.pk: t for t in tests}
    for test_id, submitted_at, score in AssessmentAttempt.objects.filter(
        assessment_id__in=list(by_id)
    ).values_list("assessment_id", "submitted_at", "score"):
        entry = stats[test_id]
        if submitted_at is None:
            entry["inProgress"] += 1
        else:
            entry["submitted"] += 1
            if score is not None and by_id[test_id].total_marks:
                entry["_pct"].append(score / by_id[test_id].total_marks * 100)

    result = []
    for t in tests:
        entry = stats[t.pk]
        scores = entry.pop("_pct")
        result.append(
            {
                **t.summary(),
                "students": group_sizes.get(t.audience_key(), 0),
                **entry,
                "averagePercentage": round(sum(scores) / len(scores), 1) if scores else None,
            }
        )
    return JsonResponse({"assessments": result, "serverTime": timezone.now()})


def create_assessment(request):
    data = json_body(request)
    institution = request.user.institution
    errors = []

    title = _text(data, "title", 200, errors, "Title", required=True, min_len=3)
    subject = _text(data, "subject", 200, errors, "Subject")
    instructions = _text(data, "instructions", 2000, errors, "Instructions")

    audience = data.get("audience")
    audience = (
        structure.find_node(institution, audience.get("level"), audience.get("id"))
        if isinstance(audience, dict)
        else None
    )
    if audience is None:
        errors.append({"field": "audience", "message": "Choose who takes this test"})

    now = timezone.now()
    raw_start = data.get("startsAt")
    starts_at = parse_datetime(raw_start) if isinstance(raw_start, str) else None
    if starts_at is None or timezone.is_naive(starts_at):
        errors.append({"field": "startsAt", "message": "Choose a valid start date and time"})
        starts_at = None
    elif starts_at < now - timedelta(minutes=5):
        errors.append({"field": "startsAt", "message": "The start time is in the past"})
    elif starts_at > now + timedelta(days=366):
        errors.append({"field": "startsAt", "message": "Schedule tests within the next year"})

    duration = _int(data, "durationMinutes", 5, 300, "Duration (minutes)", errors)
    marks = _int(data, "marksPerQuestion", 1, 100, "Marks per question", errors)

    question_ids = data.get("questionIds")
    if (
        not isinstance(question_ids, list)
        or not question_ids
        or not all(isinstance(q, str) and q for q in question_ids)
    ):
        errors.append({"field": "questionIds", "message": "Select the questions for this test"})
        question_ids = []
    elif len(question_ids) > MAX_QUESTIONS:
        errors.append({"field": "questionIds", "message": f"A test can have at most {MAX_QUESTIONS} questions"})
    elif len(set(question_ids)) != len(question_ids):
        errors.append({"field": "questionIds", "message": "Each question can only be used once"})
    count = data.get("numQuestions")
    if count is not None and count != len(question_ids):
        errors.append({"field": "numQuestions", "message": f"Select exactly {count} questions"})

    shuffle = data.get("shuffleQuestions", True)
    if not isinstance(shuffle, bool):
        errors.append({"field": "shuffleQuestions", "message": "shuffleQuestions must be true or false"})
    monitoring_fields = monitoring.clean_config(data.get("monitoring"), errors)
    v.raise_if(errors)

    try:
        bank = {str(q.pk): q for q in Question.objects.filter(institution=institution, pk__in=question_ids)}
    except ValidationError:
        bank = {}
    if any(qid not in bank for qid in question_ids):
        message = "Some selected questions aren't in your institution's question bank"
        raise BadRequest(message, [{"field": "questionIds", "message": message}])

    assessment = Assessment(
        institution=institution,
        created_by=request.user,
        title=title,
        subject=subject,
        instructions=instructions,
        starts_at=starts_at,
        duration_minutes=duration,
        marks_per_question=marks,
        shuffle_questions=shuffle,
        **monitoring_fields,
        questions=[
            {
                "id": qid,
                "text": bank[qid].text,
                "options": bank[qid].options,
                "correctAnswer": bank[qid].correct_answer,
                "explanation": bank[qid].explanation,
            }
            for qid in question_ids
        ],
    )
    assessment.set_audience(audience)
    assessment.save()
    AuditLog.record(
        institution,
        request.user,
        "assessment.created",
        f"Scheduled the test {assessment.title} for {audience.label}",
        assessmentId=str(assessment.pk),
    )
    return JsonResponse({"success": True, "assessment": assessment.summary()}, status=201)


@require_http_methods(["GET", "POST"])
@jwt_required
@role_required(*STAFF)
@api_view
def assessments(request):
    return create_assessment(request) if request.method == "POST" else list_assessments(request)


def _staff_test(request, assessment_id):
    """A test the caller may manage: its creator, or any admin of the institution."""
    assessment = _find(Assessment, assessment_id, institution=request.user.institution)
    if assessment is None or (request.user.role != "admin" and assessment.created_by_id != request.user.pk):
        return None
    return assessment


# A question needs this many submitted answers before it is flagged.
FLAG_MIN_ANSWERS = 5


def question_stats(questions, submitted):
    """How each question went, from the submitted attempts:
    {question id: {answered, skipped, correct, percentCorrect, picks: {letter: n}, flag}}.
    flag: "too_easy" (90%+ correct), "too_hard" (30% or less), "check_key" (a wrong
    option was picked more often than the right one: the question may be ambiguous
    or its answer key wrong), or None."""
    stats = {}
    for q in questions:
        letters = list(q["options"])
        picks = {letter: 0 for letter in letters}
        for attempt in submitted:
            letter = (attempt.answers or {}).get(q["id"])
            if letter in picks:
                picks[letter] += 1
        answered = sum(picks.values())
        correct = picks.get(q["correctAnswer"], 0)
        percent = round(100 * correct / answered, 1) if answered else None
        flag = None
        if answered >= FLAG_MIN_ANSWERS:
            top_wrong = max((n for letter, n in picks.items() if letter != q["correctAnswer"]), default=0)
            if top_wrong > correct:
                flag = "check_key"
            elif percent >= 90:
                flag = "too_easy"
            elif percent <= 30:
                flag = "too_hard"
        stats[q["id"]] = {
            "answered": answered,
            "skipped": len(submitted) - answered,
            "correct": correct,
            "percentCorrect": percent,
            "picks": picks,
            "flag": flag,
        }
    return stats


@require_http_methods(["GET", "PATCH", "DELETE"])
@jwt_required
@role_required(*STAFF)
@api_view
def assessment_detail(request, assessment_id):
    assessment = _staff_test(request, assessment_id)
    if assessment is None:
        return error("Test not found", 404)

    if request.method == "PATCH":
        # Monitoring rules can change until the first student starts.
        if assessment.attempts.exists():
            return error("Students have already started this test, so its monitoring rules are fixed", 400)
        data = json_body(request)
        errors = []
        fields = monitoring.clean_config(data.get("monitoring"), errors)
        v.raise_if(errors)
        for field, value in fields.items():
            setattr(assessment, field, value)
        assessment.save(update_fields=list(fields))
        AuditLog.record(
            request.user.institution,
            request.user,
            "assessment.monitoring_updated",
            f"Changed the monitoring rules of {assessment.title}",
            assessmentId=str(assessment.pk),
        )
        return JsonResponse({"success": True, "assessment": assessment.summary()})

    if request.method == "DELETE":
        if assessment.attempts.exists():
            return error("Students have already started this test, so it can't be deleted", 400)
        title = assessment.title
        assessment.delete()
        AuditLog.record(request.user.institution, request.user, "assessment.deleted", f"Deleted the test {title}")
        return HttpResponse(status=204)

    now = timezone.now()
    attempts = {}
    for attempt in AssessmentAttempt.objects.filter(assessment=assessment).select_related("assessment"):
        attempts[attempt.student_id] = sitting.finalize_if_expired(attempt, now)

    students = list(
        User.objects.filter(
            institution=request.user.institution, role="student", **assessment.audience_filter()
        ).order_by("name")
    )
    seen = {s.pk for s in students}
    # People who sat the test but have since left its group still have results.
    students += list(User.objects.filter(pk__in=[pk for pk in attempts if pk not in seen]))

    closed = assessment.status(now) == "closed"
    results = []
    for student in students:
        attempt = attempts.get(student.pk)
        if attempt is None:
            status = "missed" if closed else "not_started"
        else:
            status = "submitted" if attempt.submitted_at else "in_progress"
        results.append(
            {
                "student": {"id": str(student.pk), "name": student.name, "email": student.email},
                "status": status,
                "score": attempt.final_score if attempt else None,
                "rawScore": (attempt.raw_score if attempt.raw_score is not None else attempt.final_score)
                if attempt and attempt.submitted_at
                else None,
                "totalPenalty": attempt.total_penalty if attempt else 0,
                "submissionReason": sitting.reason_of(attempt) if attempt and attempt.submitted_at else None,
                "violations": attempt.violation_counts() if attempt else None,
                "monitoringStatus": attempt.monitoring_status if attempt else None,
                "framesAnalysed": attempt.frames_analysed if attempt else 0,
                "correct": attempt.correct if attempt and attempt.submitted_at else None,
                "percentage": _percentage(attempt, assessment) if attempt and attempt.submitted_at else None,
                "answered": len(attempt.answers) if attempt else 0,
                "submittedAt": attempt.submitted_at if attempt else None,
                "autoSubmitted": bool(attempt and attempt.auto_submitted),
            }
        )
    done = [r["percentage"] for r in results if r["percentage"] is not None]
    submitted = [a for a in attempts.values() if a.submitted_at]
    return JsonResponse(
        {
            "assessment": {**assessment.summary(), "questions": assessment.questions},
            "results": results,
            "questionStats": question_stats(assessment.questions, submitted),
            "stats": {
                "students": len(results),
                "submitted": sum(r["status"] == "submitted" for r in results),
                "inProgress": sum(r["status"] == "in_progress" for r in results),
                "averagePercentage": round(sum(done) / len(done), 1) if done else None,
                "highestPercentage": max(done) if done else None,
                "lowestPercentage": min(done) if done else None,
            },
            "serverTime": now,
        }
    )


# --------------------------------------------------------------------------- #
# Students                                                                    #
# --------------------------------------------------------------------------- #


def _student_test(request, assessment_id):
    try:
        return Assessment.for_student(request.user).filter(pk=assessment_id).first()
    except ValidationError:  # not a valid ObjectId
        return None


@require_http_methods(["GET"])
@jwt_required
@role_required("student")
def my_tests(request):
    user = request.user
    tests = list(
        Assessment.for_student(user)
        .select_related(*Assessment.AUDIENCE_FIELDS, "created_by")
        .order_by("starts_at")
    )
    now = timezone.now()
    attempts = {
        a.assessment_id: sitting.finalize_if_expired(a, now)
        for a in AssessmentAttempt.objects.filter(student=user, assessment_id__in=[t.pk for t in tests]).select_related("assessment")
    }
    items = []
    for test in tests:
        attempt = attempts.get(test.pk)
        if attempt is None:
            mine = {"status": "missed" if test.status(now) == "closed" else "not_started"}
        elif attempt.submitted_at is None:
            mine = {"status": "in_progress", "answered": len(attempt.answers)}
        else:
            mine = {
                "status": "submitted",
                "score": attempt.final_score,
                "correct": attempt.correct,
                "autoSubmitted": attempt.auto_submitted,
                "submissionReason": sitting.reason_of(attempt),
                "percentage": _percentage(attempt, test),
                "submittedAt": attempt.submitted_at,
            }
        items.append({**test.summary(), "attempt": mine})
    return JsonResponse({"tests": items, "serverTime": now})


@require_http_methods(["GET"])
@jwt_required
@role_required("student")
def my_test(request, assessment_id):
    assessment = _student_test(request, assessment_id)
    if assessment is None:
        return error("Test not found", 404)
    attempt = AssessmentAttempt.objects.filter(assessment=assessment, student=request.user).first()
    if attempt:
        attempt = sitting.finalize_if_expired(attempt)
    return JsonResponse(sitting.student_view(assessment, attempt))


@require_http_methods(["POST"])
@jwt_required
@role_required("student")
@api_view
def start_test(request, assessment_id):
    assessment = _student_test(request, assessment_id)
    if assessment is None:
        return error("Test not found", 404)
    attempt = sitting.start(assessment, request.user)
    return JsonResponse(sitting.student_view(assessment, attempt))


def _open_attempt(request, assessment_id):
    assessment = _student_test(request, assessment_id)
    if assessment is None:
        return None, error("Test not found", 404)
    attempt = (
        AssessmentAttempt.objects.filter(assessment=assessment, student=request.user)
        .select_related("assessment")
        .first()
    )
    if attempt is None:
        return None, error("Start the test first", 400)
    return attempt, None


@require_http_methods(["PUT"])
@jwt_required
@role_required("student")
@api_view
def save_test_answers(request, assessment_id):
    attempt, problem = _open_attempt(request, assessment_id)
    if problem:
        return problem
    data = json_body(request)
    sitting.save_answers(attempt, data.get("answers", {}), data.get("review", []))
    return JsonResponse({"saved": True, "savedAt": timezone.now()})


@require_http_methods(["POST"])
@jwt_required
@role_required("student")
@api_view
def submit_test(request, assessment_id):
    attempt, problem = _open_attempt(request, assessment_id)
    if problem:
        return problem
    data = json_body(request)
    attempt = sitting.submit(attempt, data.get("answers"), data.get("review"))
    return JsonResponse(sitting.student_view(attempt.assessment, attempt))


# --------------------------------------------------------------------------- #
# Monitoring                                                                  #
# --------------------------------------------------------------------------- #


def _event_dict(event, student=None):
    data = {
        "id": str(event.pk),
        "type": event.violation_type,
        "detail": event.detail,
        "occurredAt": event.occurred_at,
        "confidence": event.confidence,
        "actionTaken": event.action_taken,
        "penaltyApplied": event.penalty_applied,
        "countAfter": event.count_after,
        "reviewStatus": event.review_status,
        "reviewedAt": event.reviewed_at,
        "reviewedBy": ({"id": str(event.reviewed_by_id), "name": event.reviewed_by.name} if event.reviewed_by_id else None),
    }
    if student is not None:
        data["student"] = {"id": str(student.pk), "name": student.name}
    return data


@require_http_methods(["GET"])
@jwt_required
@role_required(*STAFF)
def monitoring_capabilities(request):
    """What this server can check, for the create-test form."""
    return JsonResponse(monitoring.capabilities())


@require_http_methods(["GET"])
@jwt_required
@role_required(*STAFF)
def assessment_violations(request, assessment_id):
    """The event timeline of a test, optionally for one student (?student=<id>)."""
    assessment = _staff_test(request, assessment_id)
    if assessment is None:
        return error("Test not found", 404)
    events = ViolationEvent.objects.filter(attempt__assessment=assessment).select_related("attempt", "reviewed_by")
    student_id = request.GET.get("student")
    try:
        if student_id:
            events = events.filter(attempt__student_id=student_id)
        events = list(events.order_by("occurred_at")[:1000])
    except ValidationError:  # ?student isn't a valid id
        return error("Student not found", 404)
    students = {u.pk: u for u in User.objects.filter(pk__in={e.attempt.student_id for e in events})}
    return JsonResponse({"events": [_event_dict(e, students.get(e.attempt.student_id)) for e in events]})


@require_http_methods(["PATCH"])
@jwt_required
@role_required(*STAFF)
@api_view
def review_violation(request, assessment_id, event_id):
    assessment = _staff_test(request, assessment_id)
    if assessment is None:
        return error("Test not found", 404)
    event = _find(ViolationEvent, event_id, attempt__assessment=assessment)
    if event is None:
        return error("Event not found", 404)
    status = json_body(request).get("reviewStatus")
    event = monitoring.review_violation(event, status, request.user)
    AuditLog.record(
        request.user.institution,
        request.user,
        "violation.reviewed",
        f"Marked a {event.violation_type.replace('_', ' ')} event as {status} in {assessment.title}",
        assessmentId=str(assessment.pk),
        eventId=str(event.pk),
    )
    attempt = event.attempt
    return JsonResponse(
        {
            "event": _event_dict(event),
            "attempt": {
                "score": attempt.final_score,
                "totalPenalty": attempt.total_penalty,
                "percentage": _percentage(attempt, assessment),
            },
        }
    )


@require_http_methods(["POST"])
@jwt_required
@role_required("student")
@api_view
def report_violation(request, assessment_id):
    attempt, problem = _open_attempt(request, assessment_id)
    if problem:
        return problem
    data = json_body(request)
    event, created = monitoring.record_violation(
        attempt,
        event_id=data.get("eventId"),
        kind=data.get("type"),
        detail=data.get("detail"),
        confidence=data.get("confidence"),
        answers=data.get("answers"),
        review=data.get("review"),
    )
    attempt.refresh_from_db()
    view = sitting.student_view(attempt.assessment, attempt)
    return JsonResponse(
        {
            "recorded": created,
            "violation": {
                "type": event.violation_type,
                "detail": event.detail,
                "actionTaken": event.action_taken,
                "penaltyApplied": event.penalty_applied,
                "countAfter": event.count_after,
            },
            # Same shape as practice tests' reports (see ai/views.py).
            "submitted": attempt.submitted_at is not None,
            "monitoring": sitting.monitoring_state(attempt),
            "test": view,
        }
    )


@require_http_methods(["POST"])
@jwt_required
@role_required("student")
@api_view
def check_frame(request, assessment_id):
    attempt, problem = _open_attempt(request, assessment_id)
    if problem:
        return problem
    try:
        result = monitoring.analyse_frame(attempt, request.FILES.get("image"))
    except monitoring.FrameRefused as refused:
        return error(refused.message, refused.status)
    return JsonResponse(result)
