"""Educator workspace: question bank, teaching overview and students.

Everything is scoped to the caller's institution. Admins can use these too.
"""
from bson import ObjectId
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from accounts.auth import jwt_required, role_required
from accounts.models import User
from ai import stats
from ai.models import PracticeAttempt
from config.csvfile import read_csv
from config.http import BadRequest, api_view, clean_query, error, json_body
from institutions import structure
from institutions.models import MODELS, AuditLog

from .models import Question

STAFF = ("admin", "educator")
LETTERS = ("A", "B", "C", "D")
DIFFICULTIES = [d for d, _ in Question.DIFFICULTY_CHOICES]
MAX_BATCH = 50
DEFAULT_PAGE = 20
MAX_PAGE = 200


def _int(raw, default, low, high):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _str(item, key, limit, required=True):
    value = item.get(key, "")
    if not isinstance(value, str):
        return None, f"{key} must be text"
    value = value.strip()
    if required and not value:
        return None, f"{key} is required"
    if len(value) > limit:
        return None, f"{key} is too long (max {limit} characters)"
    return value, None


def _clean_question(item):
    """Validate one incoming question. Returns (fields, errors)."""
    if not isinstance(item, dict):
        return None, ["must be an object"]
    errors, fields = [], {}
    for key, limit, required in (
        ("text", 2000, True),
        ("subject", 200, True),
        ("topic", 120, False),
        ("explanation", 2000, False),
    ):
        value, problem = _str(item, key, limit, required)
        if problem:
            errors.append(problem)
        fields[key] = value

    options = item.get("options")
    if not isinstance(options, dict) or set(options) != set(LETTERS):
        errors.append("options must have exactly A, B, C and D")
    else:
        cleaned = {}
        for letter in LETTERS:
            value = options[letter]
            if not isinstance(value, str) or not value.strip() or len(value) > 500:
                errors.append(f"option {letter} must be 1-500 characters of text")
            else:
                cleaned[letter] = value.strip()
        fields["options"] = cleaned

    if item.get("correctAnswer") not in LETTERS:
        errors.append("correctAnswer must be A, B, C or D")
    fields["correct_answer"] = item.get("correctAnswer")

    difficulty = item.get("difficulty", "medium")
    if difficulty not in DIFFICULTIES:
        errors.append("difficulty must be easy, medium or hard")
    fields["difficulty"] = difficulty

    ai_generated = item.get("aiGenerated", False)
    if not isinstance(ai_generated, bool):
        errors.append("aiGenerated must be true or false")
    fields["ai_generated"] = ai_generated
    return fields, errors


# --------------------------------------------------------------------------- #
# Question bank                                                               #
# --------------------------------------------------------------------------- #


def list_questions(request):
    institution = request.user.institution
    questions = Question.objects.filter(institution=institution)
    subjects = sorted(
        {s for s in questions.values_list("subject", flat=True)}, key=str.casefold
    )

    subject = clean_query(request.GET.get("subject"), 200)
    if subject:
        questions = questions.filter(subject_key=PracticeAttempt.key_for(subject))
    difficulty = request.GET.get("difficulty", "")
    if difficulty:
        if difficulty not in DIFFICULTIES:
            raise BadRequest("Unknown difficulty")
        questions = questions.filter(difficulty=difficulty)
    if request.GET.get("mine") in ("1", "true"):
        questions = questions.filter(created_by=request.user)
    query = clean_query(request.GET.get("q"))
    if query:
        questions = questions.filter(Q(text__icontains=query) | Q(topic__icontains=query))
    ids = request.GET.get("ids", "")
    if ids:
        # Specific questions, e.g. to reuse an earlier test's (comma-separated, up to 100).
        wanted = [i for i in ids.split(",") if ObjectId.is_valid(i)][:MAX_PAGE]
        questions = questions.filter(pk__in=[ObjectId(i) for i in wanted])

    total = questions.count()
    offset = _int(request.GET.get("offset"), 0, 0, 1_000_000)
    limit = _int(request.GET.get("limit"), DEFAULT_PAGE, 1, MAX_PAGE)
    page = questions.select_related("created_by").order_by("-created_at")[offset : offset + limit]
    return JsonResponse(
        {"questions": [q.to_dict() for q in page], "total": total, "subjects": subjects}
    )


def create_questions(request):
    data = json_body(request)
    items = data.get("questions")
    if not isinstance(items, list) or not items:
        raise BadRequest("Send at least one question")
    if len(items) > MAX_BATCH:
        raise BadRequest(f"Save at most {MAX_BATCH} questions at a time")

    cleaned, problems = [], []
    for i, item in enumerate(items, start=1):
        fields, errors = _clean_question(item)
        if errors:
            problems.append({"index": i, "errors": errors})
        else:
            cleaned.append(fields)
    if problems:
        first = problems[0]
        raise BadRequest(f"Question {first['index']}: {first['errors'][0]}", problems)

    institution = request.user.institution
    created = [
        Question.objects.create(
            institution=institution,
            created_by=request.user,
            subject=fields["subject"],
            subject_key=PracticeAttempt.key_for(fields["subject"]),
            topic=fields["topic"] or "",
            difficulty=fields["difficulty"],
            text=fields["text"],
            options=fields["options"],
            correct_answer=fields["correct_answer"],
            explanation=fields["explanation"] or "",
            ai_generated=fields["ai_generated"],
        )
        for fields in cleaned
    ]
    return JsonResponse(
        {"success": True, "created": len(created), "questions": [q.to_dict() for q in created]},
        status=201,
    )


@require_http_methods(["GET", "POST"])
@jwt_required
@role_required(*STAFF)
@api_view
def questions(request):
    return create_questions(request) if request.method == "POST" else list_questions(request)


# --------------------------------------------------------------------------- #
# CSV import                                                                  #
# --------------------------------------------------------------------------- #

IMPORT_COLUMNS = (
    "subject", "topic", "difficulty", "question",
    "option_a", "option_b", "option_c", "option_d", "correct_answer", "explanation",
)
REQUIRED_COLUMNS = ("question", "option_a", "option_b", "option_c", "option_d", "correct_answer")
# Other header spellings people use (keys are already lower_snake_case).
IMPORT_ALIASES = {
    "text": "question", "question_text": "question",
    "a": "option_a", "b": "option_b", "c": "option_c", "d": "option_d",
    "answer": "correct_answer", "correct": "correct_answer", "correct_option": "correct_answer", "key": "correct_answer",
    "level": "difficulty",
}
MAX_IMPORT_QUESTIONS = 500


def _text_key(text):
    return " ".join(text.split()).casefold()


def _answer_letter(raw, options):
    """A-D from "b", "Option B", "B)" or the exact text of one option; else None."""
    value = raw.strip()
    compact = value.upper().replace("OPTION", "").strip(" .):")
    if compact in LETTERS:
        return compact
    matches = [letter for letter, text in options.items() if text and _text_key(text) == _text_key(value)]
    return matches[0] if len(matches) == 1 else None


@require_http_methods(["POST"])
@jwt_required
@role_required(*STAFF)
@api_view
def import_questions(request):
    """Multipart `file` (CSV). commit=false checks every row; commit=true saves the
    valid ones. A `subject` form field fills rows whose subject cell is blank."""
    institution = request.user.institution
    commit = request.POST.get("commit") == "true"
    default_subject = " ".join(request.POST.get("subject", "").split())[:200]
    records = read_csv(
        request.FILES.get("file"),
        columns=IMPORT_COLUMNS,
        required=REQUIRED_COLUMNS if default_subject else ("subject", *REQUIRED_COLUMNS),
        aliases=IMPORT_ALIASES,
        example="subject,topic,difficulty,question,option_a,option_b,option_c,option_d,correct_answer,explanation",
        noun="questions",
        max_rows=MAX_IMPORT_QUESTIONS,
    )

    existing = {
        (subject_key, _text_key(text))
        for subject_key, text in Question.objects.filter(institution=institution).values_list("subject_key", "text")
    }
    first_line, rows = {}, []
    for line, values in records:
        options = {letter: values.get(f"option_{letter.lower()}", "") for letter in LETTERS}
        answer = values.get("correct_answer", "")
        letter = _answer_letter(answer, options) if answer else None
        difficulty = values.get("difficulty", "").lower() or "medium"
        item = {
            "text": values.get("question", ""),
            "subject": values.get("subject") or default_subject,
            "topic": values.get("topic", ""),
            "difficulty": difficulty,
            "options": options,
            "correctAnswer": letter,
            "explanation": values.get("explanation", ""),
        }
        fields, errors = _clean_question(item)
        # Friendlier wording for the mistakes people make in sheets.
        names = {"text": "Question", "subject": "Subject", "topic": "Topic", "explanation": "Explanation"}
        errors = [
            f"{names.get(e.split()[0], e.split()[0])} {e.split(' ', 1)[1]}" if " is too long " in e else e
            for e in errors
        ]
        errors = [
            "Question is missing" if e == "text is required"
            else "Subject is missing" if e == "subject is required"
            else "Difficulty must be easy, medium or hard" if e.startswith("difficulty")
            else f"Option {e[7]} is missing or longer than 500 characters" if e.startswith("option ")
            else e
            for e in errors
            if not e.startswith("correctAnswer")
        ]
        if not answer:
            errors.append("Correct answer is missing")
        elif letter is None:
            errors.append("Correct answer must be A, B, C, D or the exact text of one option")
        if not errors:
            key = (PracticeAttempt.key_for(fields["subject"]), _text_key(fields["text"]))
            if key in existing:
                errors.append("Already in the question bank")
            elif key in first_line:
                errors.append(f"Same question as row {first_line[key]}")
            else:
                first_line[key] = line
        rows.append(
            {
                "line": line,
                **{k: item[k] for k in ("text", "subject", "topic", "difficulty", "options", "correctAnswer", "explanation")},
                "errors": errors,
                "_fields": fields,
            }
        )

    public = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    valid = [r for r in rows if not r["errors"]]
    summary = {"total": len(rows), "valid": len(valid), "invalid": len(rows) - len(valid)}
    if not commit:
        return JsonResponse({"rows": public, "summary": summary})
    if not valid:
        raise BadRequest("None of the rows can be imported. Fix the problems and try again.")

    for row in valid:
        fields = row["_fields"]
        Question.objects.create(
            institution=institution,
            created_by=request.user,
            subject=fields["subject"],
            subject_key=PracticeAttempt.key_for(fields["subject"]),
            topic=fields["topic"] or "",
            difficulty=fields["difficulty"],
            text=fields["text"],
            options=fields["options"],
            correct_answer=fields["correct_answer"],
            explanation=fields["explanation"] or "",
            ai_generated=False,
        )
    subjects = sorted({r["_fields"]["subject"] for r in valid}, key=str.casefold)
    AuditLog.record(
        institution,
        request.user,
        "questions.imported",
        f"Imported {len(valid)} question{'s' if len(valid) != 1 else ''} ({', '.join(subjects)}) from a CSV file",
        created=len(valid),
        skipped=len(rows) - len(valid),
    )
    return JsonResponse(
        {"created": len(valid), "skipped": len(rows) - len(valid), "subjects": subjects, "rows": public}, status=201
    )


@require_http_methods(["DELETE"])
@jwt_required
@role_required(*STAFF)
def question_detail(request, question_id):
    try:
        question = Question.objects.filter(
            institution=request.user.institution, pk=question_id
        ).first()
    except ValidationError:
        question = None
    if question is None:
        return error("Question not found", 404)
    if request.user.role != "admin" and question.created_by_id != request.user.pk:
        return error("You can only delete questions you added", 403)
    question.delete()
    return HttpResponse(status=204)


# --------------------------------------------------------------------------- #
# Teaching overview and students                                              #
# --------------------------------------------------------------------------- #


@require_http_methods(["GET"])
@jwt_required
@role_required(*STAFF)
def overview(request):
    institution = request.user.institution
    bank = Question.objects.filter(institution=institution)
    group_stats = stats.group_stats(institution)
    sections = sorted(
        (
            structure.node_summary(node, group_stats, [node.department.batch, node.department, node])
            for node in MODELS["section"].objects.filter(institution=institution).select_related("department__batch")
        ),
        key=lambda c: (-c["studentCount"], c["label"].casefold()),
    )
    # Practice endpoints are student-only, so every attempt is a student's.
    recent_practice = PracticeAttempt.objects.filter(
        institution=institution, created_at__gte=stats.since(7)
    )
    return JsonResponse(
        {
            "counts": {
                "questions": bank.count(),
                "myQuestions": bank.filter(created_by=request.user).count(),
                "aiGenerated": bank.filter(ai_generated=True).count(),
                "students": User.objects.filter(institution=institution, role="student").count(),
                **structure.counts(institution),
            },
            "practice": {"last7Days": recent_practice.count()},
            "sections": [
                {k: c[k] for k in ("id", "name", "label", "attempts", "averageScore")} | {"students": c["studentCount"]}
                for c in sections[:8]
            ],
            "subjects": stats.subject_breakdown(stats.student_subject_rows(institution), limit=8),
            "recentQuestions": [
                q.to_dict()
                for q in bank.filter(created_by=request.user)
                .select_related("created_by")
                .order_by("-created_at")[:5]
            ],
        }
    )


@require_http_methods(["GET"])
@jwt_required
@role_required(*STAFF)
@api_view
def students(request):
    institution = request.user.institution
    members = User.objects.filter(institution=institution, role="student")

    members = structure.filter_by_groups(members, institution, request.GET)

    query = clean_query(request.GET.get("q"))
    if query:
        members = members.filter(Q(name__icontains=query) | Q(email__icontains=query))

    total = members.count()
    offset = _int(request.GET.get("offset"), 0, 0, 1_000_000)
    limit = _int(request.GET.get("limit"), 50, 1, MAX_PAGE)
    page = list(members.select_related(*User.PLACEMENT_FIELDS).order_by("name")[offset : offset + limit])
    practice = stats.student_stats(institution, [s.pk for s in page])

    return JsonResponse(
        {
            "students": [
                {
                    "id": str(s.pk),
                    "name": s.name,
                    "email": s.email,
                    "cohort": s.cohort.to_dict() if s.cohort_id else None,
                    "placement": s.placement(),
                    "lastLogin": s.last_login,
                    "mustChangePassword": s.must_change_password,
                    **practice.get(s.pk, {"attempts": 0, "averageScore": None, "lastPracticeAt": None}),
                }
                for s in page
            ],
            "total": total,
        }
    )
