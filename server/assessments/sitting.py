"""Rules for sitting a scheduled test: starting, saving answers, grading.

The server is the only clock and the only grader:
- answers are accepted only while the test is open;
- an attempt that is still open when the test closes is submitted automatically
  with whatever was saved (on the next read by anyone);
- correct answers never leave the server until the test has closed.
"""
import random
from datetime import timedelta

from django.db import IntegrityError
from django.utils import timezone

from config.http import BadRequest

from .models import AssessmentAttempt

LETTERS = ("A", "B", "C", "D")
# Accept a final submission this long after the close, for network latency.
SUBMIT_GRACE = timedelta(seconds=15)


def answer_key(assessment):
    return {q["id"]: q["correctAnswer"] for q in assessment.questions}


# Why an attempt was submitted (AssessmentAttempt.submission_reason).
STUDENT_SUBMITTED = "STUDENT_SUBMITTED"
TIME_LIMIT = "TIME_LIMIT"


def reason_of(attempt):
    """The submission reason, also for attempts submitted before reasons were recorded."""
    if attempt.submission_reason:
        return attempt.submission_reason
    return TIME_LIMIT if attempt.auto_submitted else STUDENT_SUBMITTED


def grade(attempt, *, auto=False, at=None, reason=None):
    """Score the saved answers and mark the attempt submitted, exactly once.

    Sets `attempt.graded_now`: True only for the call that finalised it. The
    final score subtracts the penalties recorded up to that moment; no penalty
    can be added afterwards (violations only apply to open attempts).
    """
    assessment = attempt.assessment
    key = answer_key(assessment)
    correct = sum(1 for qid, letter in (attempt.answers or {}).items() if key.get(qid) == letter)
    raw = float(correct * assessment.marks_per_question)
    submitted_at = at or timezone.now()
    claimed = AssessmentAttempt.objects.filter(pk=attempt.pk, submitted_at=None).update(
        submitted_at=submitted_at,
        correct=correct,
        raw_score=raw,
        auto_submitted=auto,
        submission_reason=reason or (TIME_LIMIT if auto else STUDENT_SUBMITTED),
    )
    attempt.graded_now = bool(claimed)
    if claimed:
        attempt.refresh_from_db(fields=["total_penalty"])
        score = max(0.0, raw - attempt.total_penalty)
        AssessmentAttempt.objects.filter(pk=attempt.pk).update(score=score)
    # Report the stored result (ours, or that of whoever submitted first).
    attempt.refresh_from_db()
    return attempt


def finalize_if_expired(attempt, now=None):
    """Submit an attempt left open after the test closed, as of the close time."""
    now = now or timezone.now()
    if attempt.submitted_at is None and now >= attempt.assessment.ends_at:
        return grade(attempt, auto=True, at=attempt.assessment.ends_at, reason=TIME_LIMIT)
    return attempt


def start(assessment, student):
    """The student's attempt, created on first start. Only while the test is open."""
    existing = AssessmentAttempt.objects.filter(assessment=assessment, student=student).first()
    if existing:
        return finalize_if_expired(existing)
    status = assessment.status()
    if status == "scheduled":
        raise BadRequest("This test hasn't started yet")
    if status == "closed":
        raise BadRequest("This test has closed")

    order = [q["id"] for q in assessment.questions]
    if assessment.shuffle_questions:
        random.SystemRandom().shuffle(order)
    try:
        return AssessmentAttempt.objects.create(
            assessment=assessment,
            student=student,
            order=order,
            monitoring_status="active" if assessment.monitoring_enabled else "off",
        )
    except IntegrityError:  # started in another tab at the same moment
        return AssessmentAttempt.objects.get(assessment=assessment, student=student)


def clean_answers(assessment, answers, review):
    """Validate an autosave payload. Unanswered questions are simply absent."""
    ids = {q["id"] for q in assessment.questions}
    if not isinstance(answers, dict):
        raise BadRequest("answers must be an object of question id to A, B, C or D")
    cleaned = {}
    for qid, letter in answers.items():
        if qid not in ids:
            raise BadRequest("An answer refers to a question that isn't in this test")
        if letter in ("", None):
            continue
        if letter not in LETTERS:
            raise BadRequest("Answers must be A, B, C or D")
        cleaned[qid] = letter
    if review is None:
        review = []
    if not isinstance(review, list) or any(qid not in ids for qid in review):
        raise BadRequest("review must be a list of question ids from this test")
    return cleaned, list(dict.fromkeys(review))  # de-duplicated, order kept


def save_answers(attempt, answers, review):
    """Autosave while the test is open; refuses once submitted or closed."""
    if attempt.submitted_at is not None:
        raise BadRequest("This test was already submitted")
    if timezone.now() >= attempt.assessment.ends_at:
        finalize_if_expired(attempt)
        raise BadRequest("Time is up. Your saved answers were submitted.")
    cleaned, review = clean_answers(attempt.assessment, answers, review)
    saved = AssessmentAttempt.objects.filter(pk=attempt.pk, submitted_at=None).update(
        answers=cleaned, review=review
    )
    if not saved:
        raise BadRequest("This test was already submitted")
    attempt.answers, attempt.review = cleaned, review
    return attempt


def submit(attempt, answers=None, review=None):
    """Final submission. Late payloads (past the grace period) are ignored and
    the answers saved before the close are graded instead. Anything arriving
    at or after the close is the timer running out, so it counts as automatic
    and is recorded at the close time."""
    if attempt.submitted_at is not None:
        return attempt
    now = timezone.now()
    ends_at = attempt.assessment.ends_at
    if answers is not None and now <= ends_at + SUBMIT_GRACE:
        cleaned, review = clean_answers(attempt.assessment, answers, review)
        AssessmentAttempt.objects.filter(pk=attempt.pk, submitted_at=None).update(
            answers=cleaned, review=review
        )
        attempt.answers, attempt.review = cleaned, review
    if now >= ends_at:
        return grade(attempt, auto=True, at=ends_at, reason=TIME_LIMIT)
    return grade(attempt, reason=STUDENT_SUBMITTED)


def monitoring_state(attempt):
    """Monitoring rules and this attempt's counts, for the student's browser."""
    return {
        **attempt.assessment.monitoring_config(),
        "counts": attempt.violation_counts(),
        "totalPenalty": attempt.total_penalty,
    }


def student_view(assessment, attempt, now=None):
    """What a student may see right now. Answer keys only after the close."""
    now = now or timezone.now()
    status = assessment.status(now)
    data = {**assessment.summary(), "serverTime": now}

    if attempt is None:
        data["attempt"] = {"status": "missed" if status == "closed" else "not_started"}
        return data

    by_id = {q["id"]: q for q in assessment.questions}
    if attempt.submitted_at is None:
        data["attempt"] = {
            "status": "in_progress",
            "startedAt": attempt.started_at,
            "answers": attempt.answers,
            "review": attempt.review,
            "monitoring": monitoring_state(attempt),
            "questions": [
                {"id": qid, "text": by_id[qid]["text"], "options": by_id[qid]["options"]}
                for qid in attempt.order
                if qid in by_id
            ],
        }
        return data

    final = attempt.final_score
    result = {
        "status": "submitted",
        "submittedAt": attempt.submitted_at,
        "autoSubmitted": attempt.auto_submitted,
        "submissionReason": reason_of(attempt),
        "correct": attempt.correct,
        "rawScore": attempt.raw_score if attempt.raw_score is not None else final,
        "totalPenalty": attempt.total_penalty,
        "score": final,
        "percentage": round(final / assessment.total_marks * 100, 1) if assessment.total_marks else 0,
        "answered": len(attempt.answers),
        "violations": attempt.violation_counts() if assessment.monitoring_enabled else None,
    }
    if status == "closed":
        result["review"] = [
            {
                "id": qid,
                "text": by_id[qid]["text"],
                "options": by_id[qid]["options"],
                "correctAnswer": by_id[qid]["correctAnswer"],
                "explanation": by_id[qid].get("explanation", ""),
                "yourAnswer": attempt.answers.get(qid),
            }
            for qid in attempt.order
            if qid in by_id
        ]
    data["attempt"] = result
    return data
