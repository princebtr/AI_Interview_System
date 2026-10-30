import logging
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.auth import jwt_required, role_required
from config.http import BadRequest, api_view, error, json_body

from . import proctoring, services, stats, vision
from .gemini import GeminiError
from .models import InterviewSession, PracticeAttempt, PracticeQuestion, PracticeQuiz

logger = logging.getLogger(__name__)

MAX_SUBJECT_LEN = 200
MAX_TOPICS_LEN = 120
MAX_TEXT_LEN = 5000

STUDENT = ("student",)
EVERYONE = ("admin", "educator", "student")


def _text(data, key, limit, required=True):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise BadRequest(f"{key} must be text")
    value = value.strip()
    if required and not value:
        raise BadRequest(f"{key} is required")
    if len(value) > limit:
        raise BadRequest(f"{key} is too long")
    return value


def ai_view(*roles):
    """Auth + role check + POST-only + JSON error handling for an AI endpoint."""

    def decorator(view):
        view = api_view(view)
        view = role_required(*roles)(view)
        view = jwt_required(view)
        return require_http_methods(["POST"])(view)

    return decorator


def _gemini_guard(fn):
    try:
        return fn()
    except GeminiError as exc:
        return error(str(exc), 502)


def _own(model, request, pk):
    """The caller's own record with that id, or None (never another user's)."""
    if not isinstance(pk, str) or not pk:
        return None
    try:
        return model.objects.filter(pk=pk, user=request.user).first()
    except ValidationError:  # not a valid ObjectId
        return None


def _record(request, kind, subject, score, correct=None, total=None):
    PracticeAttempt.objects.create(
        institution=request.user.institution,
        user=request.user,
        kind=kind,
        subject=subject,
        subject_key=PracticeAttempt.key_for(subject),
        score=score,
        correct=correct,
        total=total,
    )


# --- AI interview (students) --------------------------------------------------


@ai_view(*STUDENT)
def generate_question(request):
    subject = _text(json_body(request), "subject", MAX_SUBJECT_LEN)

    def run():
        text = services.generate_question(subject)
        question = PracticeQuestion.objects.create(
            institution=request.user.institution, user=request.user, subject=subject, text=text
        )
        return JsonResponse({"question": text, "questionId": str(question.pk)})

    return _gemini_guard(run)


@ai_view(*STUDENT)
def evaluate_answer(request):
    data = json_body(request)
    answer = _text(data, "answer", MAX_TEXT_LEN)
    question = _own(PracticeQuestion, request, data.get("questionId"))
    if question is None:
        raise BadRequest("Unknown question. Ask for a new one and try again.")
    if question.answered_at:
        raise BadRequest("This question was already answered. Ask for a new one.")

    def run():
        score = services.evaluate_answer(question.text, answer)
        # Mark answered only if it's still open, so a double submit isn't scored twice.
        claimed = PracticeQuestion.objects.filter(pk=question.pk, answered_at=None).update(
            answered_at=timezone.now()
        )
        if not claimed:
            raise BadRequest("This question was already answered. Ask for a new one.")
        _record(request, "interview", question.subject, score * 10)
        return JsonResponse({"evaluation": str(score), "score": score})

    return _gemini_guard(run)


# --- Multiple-choice: practice for students, authoring for staff ---------------


@ai_view(*EVERYONE)
def generate_mcq_questions(request):
    data = json_body(request)
    subject = _text(data, "subject", MAX_SUBJECT_LEN)
    topics = _text(data, "topics", MAX_TOPICS_LEN, required=False)
    difficulty = data.get("difficulty", "medium")
    if difficulty not in services.DIFFICULTIES:
        raise BadRequest("Difficulty must be easy, medium or hard")
    count = data.get("numQuestions", 5)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 20:
        raise BadRequest("Number of questions must be between 1 and 20")

    def run():
        questions = services.generate_mcq(subject, count, difficulty, topics)
        if request.user.role != "student":
            # Educators and admins review answer keys before saving to the bank.
            return JsonResponse({"questions": questions})
        # Practice tests are proctored like scheduled tests (camera checks where
        # the server can run them).
        quiz = PracticeQuiz.objects.create(
            institution=request.user.institution,
            user=request.user,
            subject=subject,
            questions=questions,
            proctored=True,
            camera_checks=vision.available(),
        )
        public = [{k: q[k] for k in ("id", "question", "options")} for q in questions]
        return JsonResponse(
            {"quizId": str(quiz.pk), "questions": public, "monitoring": proctoring.practice_state(quiz)}
        )

    return _gemini_guard(run)


@ai_view(*STUDENT)
def evaluate_mcq_answers(request):
    data = json_body(request)
    answers = data.get("userAnswers")
    if not isinstance(answers, dict) or not answers:
        raise BadRequest("Answers are required")
    quiz = _own(PracticeQuiz, request, data.get("quizId"))
    if quiz is None:
        raise BadRequest("Unknown practice test. Generate a new one and try again.")

    # Graded and recorded once: a second submission (or one after proctoring
    # submitted the test) is refused.
    quiz = proctoring.submit_practice(quiz, answers, proctoring.STUDENT_SUBMITTED)
    if not quiz.graded_now:
        raise BadRequest(proctoring.PRACTICE_CLOSED)
    return JsonResponse(proctoring.practice_result(quiz))


# --- Practice test proctoring (students) ------------------------------------------


def _practice_quiz(request, quiz_id):
    quiz = _own(PracticeQuiz, request, quiz_id)
    if quiz is None:
        return None, error("Practice test not found", 404)
    return quiz, None


@require_http_methods(["GET"])
@jwt_required
@role_required(*STUDENT)
def practice_status(request, quiz_id):
    """A practice test's proctoring state, and its result once submitted (e.g. by
    proctoring while the browser was offline)."""
    quiz, problem = _practice_quiz(request, quiz_id)
    if problem:
        return problem
    submitted = quiz.submitted_at is not None
    return JsonResponse(
        {
            "submitted": submitted,
            "monitoring": proctoring.practice_state(quiz),
            "result": proctoring.practice_result(quiz) if submitted else None,
        }
    )


@ai_view(*STUDENT)
def practice_violation(request, quiz_id):
    quiz, problem = _practice_quiz(request, quiz_id)
    if problem:
        return problem
    data = json_body(request)
    event, created = proctoring.record_practice_violation(
        quiz,
        event_id=data.get("eventId"),
        kind=data.get("type"),
        detail=data.get("detail"),
        confidence=data.get("confidence"),
        answers=data.get("answers"),
    )
    quiz.refresh_from_db()
    submitted = quiz.submitted_at is not None
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
            "submitted": submitted,
            "monitoring": proctoring.practice_state(quiz),
            "result": proctoring.practice_result(quiz) if submitted else None,
        }
    )


@ai_view(*STUDENT)
def practice_frame(request, quiz_id):
    quiz, problem = _practice_quiz(request, quiz_id)
    if problem:
        return problem
    try:
        result = proctoring.practice_camera_check(quiz, request.FILES.get("image"))
    except proctoring.FrameRefused as refused:
        return error(refused.message, refused.status)
    return JsonResponse(result)


# --- Proctoring (students) ------------------------------------------------------


@require_http_methods(["GET"])
@jwt_required
@role_required(*STUDENT)
def proctoring_config(request):
    return JsonResponse({"cameraChecks": vision.available(), "detection": proctoring.detection_config()})


@ai_view(*STUDENT)
def analyse_frame(request):
    """One webcam frame from an AI interview: people, faces, phones."""
    try:
        result = proctoring.interview_camera_check(request.user, request.FILES.get("image"))
    except proctoring.FrameRefused as refused:
        return error(refused.message, refused.status)
    return JsonResponse(result)


# Older single-purpose checks, kept for API compatibility.
@ai_view(*STUDENT)
def detect_faces(request):
    frame, _ = vision.read_image(request.FILES.get("image"))
    return JsonResponse({"count": vision.count_people(frame)})


@ai_view(*STUDENT)
def detect_phone(request):
    frame, _ = vision.read_image(request.FILES.get("image"))
    return JsonResponse({"phone_detected": vision.phone_present(frame)})


@ai_view(*STUDENT)
def start_session(request):
    path = ""
    upload = request.FILES.get("screenshot")
    if upload is not None:
        _, data = vision.read_image(upload)
        folder = Path(settings.MEDIA_ROOT) / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"interview_{uuid.uuid4().hex}.jpg"
        (folder / filename).write_bytes(data)
        path = f"screenshots/{filename}"

    InterviewSession.objects.create(
        institution=request.user.institution, user=request.user, screenshot_path=path
    )
    return JsonResponse({"message": "Interview session started successfully!"})


# --- Student performance ----------------------------------------------------------


@require_http_methods(["GET"])
@jwt_required
@role_required(*STUDENT)
def my_performance(request):
    attempts = PracticeAttempt.objects.filter(user=request.user).order_by("-created_at")
    rows = list(attempts.values_list("subject", "subject_key", "score", "kind", "created_at"))

    scores = [score for _, _, score, _, _ in rows]
    interview = [score for _, _, score, kind, _ in rows if kind == "interview"]
    subjects = stats.subject_breakdown((s, k, score) for s, k, score, _, _ in rows)
    improve = [
        s["subject"]
        for s in sorted(subjects, key=lambda s: s["averageScore"])
        if s["averageScore"] is not None and s["averageScore"] < 70
    ][:3]

    return JsonResponse(
        {
            "summary": {
                "overall": stats.average(scores),
                "attempts": len(rows),
                "assessments": sum(kind == "mcq" for _, _, _, kind, _ in rows),
                "interviewAnswers": len(interview),
                "interviewAverage": stats.average(interview),
                "streakDays": stats.streak_days(ts for *_, ts in rows),
            },
            "subjects": subjects,
            "improve": improve,
            "recent": [a.to_dict() for a in attempts[:20]],
        }
    )
