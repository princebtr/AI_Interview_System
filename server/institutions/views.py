"""Institution administration: members (users) and cohorts.

Every query is scoped to the requesting user's institution, so one tenant can
never read or reference another tenant's records.
"""
import csv
import io

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from accounts import validators as v
from accounts.auth import jwt_required, role_required
from accounts.models import User
from accounts.passwords import generate_password, hash_many
from accounts.throttle import clear_attempts, throttle_key
from ai import stats
from ai.models import PracticeAttempt
from config.http import BadRequest, api_view, clean_query, error, json_body

from . import validators as institution_rules
from .branding import process_logo
from .models import AuditLog, Cohort, Institution
from .theme import theme_dict

ROLES = [role for role, _ in User.ROLE_CHOICES]
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_SEARCH_LEN = 100
MAX_OFFSET = 1_000_000
MAX_COHORT_NAME = 60
MAX_IMPORT_ROWS = 500
MAX_IMPORT_BYTES = 1024 * 1024
ROLE_LABELS = dict(User.ROLE_CHOICES)


def find_member(institution, user_id):
    """This institution's user with that id, or None."""
    try:
        return User.objects.filter(institution=institution, pk=user_id).select_related("cohort").first()
    except ValidationError:
        return None


def member_dict(user):
    return {
        "id": str(user.pk),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "cohort": user.cohort.to_dict() if user.cohort_id else None,
        "mustChangePassword": user.must_change_password,
        "lastLogin": user.last_login,
        "createdAt": user.created_at,
    }


def find_cohort(institution, cohort_id):
    """This institution's cohort with that id, or None. Never another tenant's."""
    if not isinstance(cohort_id, str) or not cohort_id.strip():
        return None
    try:
        return Cohort.objects.filter(institution=institution, pk=cohort_id.strip()).first()
    except ValidationError:  # not a valid ObjectId
        return None


def parse_int(raw, default, *, low, high=None):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    value = max(low, value)
    return min(high, value) if high is not None else value


# --------------------------------------------------------------------------- #
# Users                                                                        #
# --------------------------------------------------------------------------- #


def list_users(request):
    institution = request.user.institution
    members = User.objects.filter(institution=institution)
    counts = {role: members.filter(role=role).count() for role in ROLES}

    role = request.GET.get("role", "").strip()
    if role:
        if role not in ROLES:
            raise BadRequest("Unknown role filter")
        members = members.filter(role=role)

    cohort_id = request.GET.get("cohort", "").strip()
    if cohort_id:
        cohort = find_cohort(institution, cohort_id)
        if cohort is None:
            raise BadRequest("Unknown cohort")
        members = members.filter(cohort=cohort)

    query = clean_query(request.GET.get("q"), MAX_SEARCH_LEN)
    if query:
        members = members.filter(Q(name__icontains=query) | Q(email__icontains=query))

    total = members.count()
    offset = parse_int(request.GET.get("offset"), 0, low=0, high=MAX_OFFSET)
    limit = parse_int(request.GET.get("limit"), DEFAULT_PAGE_SIZE, low=1, high=MAX_PAGE_SIZE)
    page = members.select_related("cohort").order_by("-created_at")[offset : offset + limit]

    return JsonResponse(
        {"users": [member_dict(u) for u in page], "total": total, "counts": counts}
    )


def create_user(request):
    data = json_body(request)
    institution = request.user.institution
    errors = []

    name = v.clean_name(data, errors)
    email = v.clean_email(data, errors)
    role = data.get("role")
    if role not in ROLES:
        errors.append({"field": "role", "message": "Choose a role: admin, educator or student"})
    password = v.clean_new_password(data.get("password"), errors)

    cohort = None
    if role == "student":
        cohort = find_cohort(institution, data.get("cohortId"))
        if cohort is None:
            errors.append({"field": "cohortId", "message": "Choose a cohort for this student"})

    require_change = data.get("requirePasswordChange", True)
    if not isinstance(require_change, bool):
        errors.append(
            {"field": "requirePasswordChange", "message": "requirePasswordChange must be true or false"}
        )
    v.raise_if(errors)

    duplicate = [{"field": "email", "message": "An account with this email already exists"}]
    if User.objects.filter(email=email).exists():
        return error(duplicate[0]["message"], 400, errors=duplicate)

    user = User(
        institution=institution,
        cohort=cohort,
        name=name,
        email=email,
        role=role,
        must_change_password=require_change,
    )
    user.set_password(password)
    try:
        user.save()
    except IntegrityError:  # lost a race with another request for the same email
        return error(duplicate[0]["message"], 400, errors=duplicate)
    where = f" in {cohort.name}" if cohort else ""
    AuditLog.record(
        institution,
        request.user,
        "user.created",
        f"Added {user.name} as {ROLE_LABELS[role].lower()}{where}",
        userId=str(user.pk),
    )
    return JsonResponse({"success": True, "user": member_dict(user)}, status=201)


@require_http_methods(["GET", "POST"])
@jwt_required
@role_required("admin")
@api_view
def users(request):
    return create_user(request) if request.method == "POST" else list_users(request)


# --------------------------------------------------------------------------- #
# Cohorts                                                                      #
# --------------------------------------------------------------------------- #


def cohort_dict(cohort, student_count=0):
    return {**cohort.to_dict(), "studentCount": student_count}


def list_cohorts(request):
    return JsonResponse({"cohorts": stats.cohort_stats(request.user.institution)})


def create_cohort(request):
    if request.user.role != "admin":
        return error("Only admins can create cohorts", 403)
    institution = request.user.institution
    data = json_body(request)
    name = data.get("name")
    name = Cohort.clean_name(name) if isinstance(name, str) else ""

    if not name:
        raise BadRequest("Enter a cohort name", [{"field": "name", "message": "Enter a cohort name"}])
    if len(name) > MAX_COHORT_NAME:
        message = f"Cohort names can be at most {MAX_COHORT_NAME} characters"
        raise BadRequest(message, [{"field": "name", "message": message}])

    taken = f'A cohort named "{name}" already exists'
    if Cohort.objects.filter(institution=institution, name_key=Cohort.key_for(name)).exists():
        raise BadRequest(taken, [{"field": "name", "message": taken}])
    try:
        cohort = Cohort.objects.create(institution=institution, name=name)
    except IntegrityError:
        raise BadRequest(taken, [{"field": "name", "message": taken}])
    AuditLog.record(institution, request.user, "cohort.created", f"Created the cohort {cohort.name}")
    return JsonResponse({"success": True, "cohort": cohort_dict(cohort)}, status=201)


@require_http_methods(["GET", "POST"])
@jwt_required
@role_required("admin", "educator")
@api_view
def cohorts(request):
    return create_cohort(request) if request.method == "POST" else list_cohorts(request)


@require_http_methods(["GET", "DELETE"])
@jwt_required
@role_required("admin", "educator")
def cohort_detail(request, cohort_id):
    institution = request.user.institution
    cohort = find_cohort(institution, cohort_id)
    if cohort is None:
        return error("Cohort not found", 404)

    if request.method == "GET":
        return JsonResponse({"cohort": stats.cohort_stats(institution, [cohort.pk])[0]})

    if request.user.role != "admin":
        return error("Only admins can delete cohorts", 403)
    if User.objects.filter(cohort=cohort).exists():
        return error("Move or remove this cohort's students before deleting it", 400)
    if cohort.assessments.exists():
        return error("This cohort has tests assigned to it, so it can't be deleted", 400)
    name = cohort.name
    cohort.delete()
    AuditLog.record(institution, request.user, "cohort.deleted", f"Deleted the cohort {name}")
    return HttpResponse(status=204)


# --------------------------------------------------------------------------- #
# Dashboard                                                                    #
# --------------------------------------------------------------------------- #


@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def overview(request):
    institution = request.user.institution
    members = User.objects.filter(institution=institution)
    recent = list(
        PracticeAttempt.objects.filter(
            institution=institution, created_at__gte=stats.since(14)
        ).values_list("created_at", flat=True)
    )
    week_ago = stats.since(7)
    last_week = sum(ts >= week_ago for ts in recent)
    month_scores = PracticeAttempt.objects.filter(
        institution=institution, created_at__gte=stats.since(30)
    ).values_list("score", flat=True)
    cohorts = sorted(
        stats.cohort_stats(institution), key=lambda c: (-c["studentCount"], c["name"].casefold())
    )

    return JsonResponse(
        {
            "counts": {
                "students": members.filter(role="student").count(),
                "educators": members.filter(role="educator").count(),
                "admins": members.filter(role="admin").count(),
                "cohorts": len(cohorts),
            },
            "activatedStudents": members.filter(role="student", last_login__isnull=False).count(),
            "practice": {
                "last7Days": last_week,
                "previous7Days": len(recent) - last_week,
                "averageScore": stats.average(month_scores),
                "daily": stats.daily_counts(recent, 14),
            },
            "cohorts": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "students": c["studentCount"],
                    "activated": c["activated"],
                    "averageScore": c["averageScore"],
                }
                for c in cohorts[:6]
            ],
        }
    )


@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def activity(request):
    limit = parse_int(request.GET.get("limit"), 20, low=1, high=100)
    logs = (
        AuditLog.objects.filter(institution=request.user.institution)
        .select_related("actor")
        .order_by("-created_at")[:limit]
    )
    return JsonResponse({"activity": [log.to_dict() for log in logs]})


# --------------------------------------------------------------------------- #
# Password reset                                                               #
# --------------------------------------------------------------------------- #


@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@api_view
def reset_password(request, user_id):
    institution = request.user.institution
    target = find_member(institution, user_id)
    if target is None:
        return error("User not found", 404)
    if target.pk == request.user.pk:
        raise BadRequest("Change your own password in Settings")

    password = json_body(request).get("password") or None
    if password is None:
        password = generate_password()
    else:
        errors = []
        v.clean_new_password(password, errors)
        v.raise_if(errors)

    target.set_password(password)
    target.must_change_password = True
    target.token_version += 1  # sign them out everywhere
    target.save(update_fields=["password", "must_change_password", "token_version", "updated_at"])
    clear_attempts(throttle_key("login", target.email))
    AuditLog.record(
        institution, request.user, "user.password_reset", f"Reset the password for {target.name}"
    )
    return JsonResponse({"success": True, "user": member_dict(target), "password": password})


# --------------------------------------------------------------------------- #
# CSV import                                                                   #
# --------------------------------------------------------------------------- #

IMPORT_COLUMNS = ("name", "email", "role", "password", "cohort")
REQUIRED_COLUMNS = ("name", "email", "role")


def _read_csv(upload):
    """[(line number, {column: value})] for every non-blank data row."""
    if upload is None:
        raise BadRequest("Choose a CSV file to import")
    if upload.size > MAX_IMPORT_BYTES:
        raise BadRequest("The file is larger than 1 MB. Split it into smaller files.")
    raw = upload.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")  # Excel on Windows

    reader = csv.reader(io.StringIO(text, newline=""))
    rows = []
    try:
        for row in reader:
            if any(cell.strip() for cell in row):
                rows.append((reader.line_num, row))
    except csv.Error:
        raise BadRequest("That file isn't valid CSV. Save it as CSV and try again.")
    if not rows:
        raise BadRequest("The file is empty")

    columns = [cell.strip().lower() for cell in rows[0][1]]
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise BadRequest(
            f"Missing column{'s' if len(missing) > 1 else ''}: {', '.join(missing)}. "
            "The first row must be a header such as name,email,role,password,cohort."
        )
    if len(set(columns)) != len(columns):
        raise BadRequest("The header repeats a column name")

    body = rows[1:]
    if not body:
        raise BadRequest("The file has a header but no people")
    if len(body) > MAX_IMPORT_ROWS:
        raise BadRequest(f"Import at most {MAX_IMPORT_ROWS} people at a time")

    index = {c: columns.index(c) for c in IMPORT_COLUMNS if c in columns}
    return [
        (line, {c: (row[i].strip() if i < len(row) else "") for c, i in index.items()})
        for line, row in body
    ]


def _check_rows(institution, records, create_cohorts):
    """Validate every row. Returns (rows, cohorts by key, cohorts to create, unknown cohorts)."""
    cohorts = {c.name_key: c for c in Cohort.objects.filter(institution=institution)}
    emails = [values.get("email", "").lower() for _, values in records]
    taken = set(User.objects.filter(email__in=[e for e in emails if e]).values_list("email", flat=True))
    first_line = {}
    to_create, unknown = {}, {}
    rows = []

    for line, values in records:
        errors = []
        name = " ".join(values.get("name", "").split())
        email = values.get("email", "").lower()
        role = values.get("role", "").lower()
        password = values.get("password", "")
        cohort_name = Cohort.clean_name(values.get("cohort", "")) if role == "student" else ""

        if not 2 <= len(name) <= 50:
            errors.append("Name is missing" if not name else "Name must be 2-50 characters")
        try:
            validate_email(email)
        except ValidationError:
            errors.append("Email is missing" if not email else "Email isn't valid")
        else:
            if email in taken:
                errors.append("An account with this email already exists")
            elif email in first_line:
                errors.append(f"Same email as row {first_line[email]}")
            else:
                first_line[email] = line
        if role not in ROLE_LABELS:
            errors.append("Role must be admin, educator or student")
        if password:
            problems = []
            v.clean_new_password(password, problems)
            errors += [p["message"] for p in problems]
        if role == "student":
            key = Cohort.key_for(cohort_name)
            if not cohort_name:
                errors.append("Students need a cohort")
            elif len(cohort_name) > MAX_COHORT_NAME:
                errors.append(f"Cohort names can be at most {MAX_COHORT_NAME} characters")
            elif key not in cohorts:
                if create_cohorts:
                    to_create.setdefault(key, cohort_name)
                else:
                    unknown.setdefault(key, cohort_name)
                    errors.append(f'Cohort "{cohort_name}" doesn\'t exist')

        rows.append(
            {
                "line": line,
                "name": name,
                "email": email,
                "role": role if role in ROLE_LABELS else values.get("role", ""),
                "cohort": cohort_name,
                "passwordProvided": bool(password),
                "errors": errors,
                "_password": password,
            }
        )
    return rows, cohorts, to_create, unknown


def _public(row):
    return {k: val for k, val in row.items() if not k.startswith("_")}


@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@api_view
def import_users(request):
    institution = request.user.institution
    commit = request.POST.get("commit") == "true"
    create_cohorts = request.POST.get("createCohorts") == "true"
    records = _read_csv(request.FILES.get("file"))
    rows, cohorts, to_create, unknown = _check_rows(institution, records, create_cohorts)
    valid = [r for r in rows if not r["errors"]]

    summary = {"total": len(rows), "valid": len(valid), "invalid": len(rows) - len(valid)}
    if not commit:
        return JsonResponse(
            {
                "rows": [_public(r) for r in rows],
                "summary": summary,
                "missingCohorts": sorted(unknown.values(), key=str.casefold),
                "newCohorts": sorted(to_create.values(), key=str.casefold),
            }
        )
    if not valid:
        raise BadRequest("None of the rows can be imported. Fix the problems and try again.")

    created_cohorts = []
    needed = {Cohort.key_for(r["cohort"]) for r in valid if r["role"] == "student"}
    for key, name in to_create.items():
        if key not in needed:
            continue
        try:
            cohorts[key] = Cohort.objects.create(institution=institution, name=name)
            created_cohorts.append(cohorts[key].name)
        except IntegrityError:  # created concurrently
            cohorts[key] = Cohort.objects.get(institution=institution, name_key=key)

    passwords = [r["_password"] or generate_password() for r in valid]
    hashes = hash_many(passwords)
    created, credentials = 0, []
    for row, password, hashed in zip(valid, passwords, hashes):
        user = User(
            institution=institution,
            cohort=cohorts[Cohort.key_for(row["cohort"])] if row["role"] == "student" else None,
            name=row["name"],
            email=row["email"],
            role=row["role"],
            password=hashed,
            must_change_password=True,
        )
        try:
            user.save()
        except IntegrityError:  # email claimed since validation
            row["errors"].append("An account with this email already exists")
            continue
        created += 1
        if not row["_password"]:
            credentials.append({"name": user.name, "email": user.email, "password": password})

    if created:
        extra = f" and created {', '.join(created_cohorts)}" if created_cohorts else ""
        AuditLog.record(
            institution,
            request.user,
            "users.imported",
            f"Imported {created} user{'s' if created != 1 else ''} from a CSV file{extra}",
            created=created,
            skipped=len(rows) - created,
        )
    return JsonResponse(
        {
            "created": created,
            "skipped": len(rows) - created,
            "credentials": credentials,
            "cohortsCreated": created_cohorts,
            "rows": [_public(r) for r in rows],
        },
        status=201,
    )


# --------------------------------------------------------------------------- #
# Institution profile and branding                                             #
# --------------------------------------------------------------------------- #


@require_http_methods(["GET", "PATCH"])
@jwt_required
@api_view
def profile(request):
    institution = request.user.institution
    if request.method == "GET":
        return JsonResponse({"institution": institution.to_dict()})
    if request.user.role != "admin":
        return error("Only admins can change institution details", 403)

    data = json_body(request)
    errors, changed = [], []

    if "name" in data:
        name = " ".join(data["name"].split()) if isinstance(data["name"], str) else ""
        problem = institution_rules.name_error(name, exclude=institution)
        if problem:
            errors.append({"field": "name", "message": problem})
        elif name != institution.name:
            institution.name = name
            changed.append("name")
    if "academicYear" in data:
        year = data["academicYear"].strip() if isinstance(data["academicYear"], str) else ""
        problem = institution_rules.academic_year_error(year)
        if problem:
            errors.append({"field": "academicYear", "message": problem})
        elif year != institution.academic_year:
            institution.academic_year = year
            changed.append("academic_year")
    if "website" in data:
        website = institution_rules.clean_website(data["website"]) if isinstance(data["website"], str) else None
        problem = "Enter a valid website URL." if website is None else (
            institution_rules.website_error(website) if website else None
        )
        if problem:
            errors.append({"field": "website", "message": problem})
        elif website != institution.website:
            institution.website = website
            changed.append("website")
    v.raise_if(errors)

    if changed:
        institution.save(update_fields=changed + ["updated_at"])
        summary = (
            f"Renamed the institution to {institution.name}"
            if changed == ["name"]
            else "Updated the institution details"
        )
        AuditLog.record(institution, request.user, "institution.updated", summary, fields=changed)
    return JsonResponse({"success": True, "institution": institution.to_dict()})


@require_http_methods(["POST", "DELETE"])
@jwt_required
@role_required("admin")
@api_view
def institution_logo(request):
    institution = request.user.institution
    if request.method == "DELETE":
        institution.logo, institution.logo_version = None, ""
        action, summary = "institution.logo_removed", "Removed the institution logo"
    else:
        institution.logo, institution.logo_version = process_logo(request.FILES.get("logo"))
        action, summary = "institution.logo_updated", "Updated the institution logo"
    institution.save(update_fields=["logo", "logo_version", "updated_at"])
    AuditLog.record(institution, request.user, action, summary)
    return JsonResponse({"success": True, "institution": institution.to_dict()})


@require_http_methods(["GET"])
def logo(request, institution_id):
    """Public: the logo appears in <img> tags, which can't send a Bearer token.
    Logos aren't sensitive, and institution ids aren't enumerable listings."""
    try:
        institution = (
            Institution.objects.only("logo", "logo_version", "is_active").filter(pk=institution_id).first()
        )
    except ValidationError:
        institution = None
    if institution is None or not institution.is_active or not institution.logo:
        return HttpResponse(status=404)

    response = HttpResponse(bytes(institution.logo), content_type="image/png")
    versioned = request.GET.get("v") == institution.logo_version
    response["Cache-Control"] = "public, max-age=31536000, immutable" if versioned else "public, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'"
    response["Cross-Origin-Resource-Policy"] = "cross-origin"  # shown by the client on another origin
    return response


@require_http_methods(["GET"])
def branding(request, slug):
    """Public: name, logo and colours for an institution's sign-in page (/login?school=<slug>)."""
    institution = (
        Institution.objects.defer("logo").filter(slug=slug, is_active=True).first()
    )
    if institution is None:
        return error("Institution not found", 404)
    return JsonResponse(
        {
            "name": institution.name,
            "type": institution.type,
            "slug": institution.slug,
            "logoUrl": institution.logo_url,
            "theme": theme_dict(institution),
        }
    )
