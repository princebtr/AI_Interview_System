"""Reports: a student's own, any student's (for staff), and an overview of
the institution or one of its groups (for staff). All scoped to the caller's
institution; ?days= picks the window (30, 90, 180 or 365; default 90)."""
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from accounts.auth import jwt_required, role_required
from accounts.models import User
from config.http import BadRequest, api_view, error
from institutions import structure
from institutions.models import LEVELS

from . import analytics

STAFF = ("admin", "educator")


def _days(request):
    raw = request.GET.get("days", "").strip()
    if not raw:
        return analytics.DEFAULT_RANGE
    try:
        days = int(raw)
    except ValueError:
        days = None
    if days not in analytics.RANGES:
        raise BadRequest(f"days must be one of {', '.join(map(str, analytics.RANGES))}")
    return days


def _student_dict(student):
    return {
        "id": str(student.pk),
        "name": student.name,
        "email": student.email,
        "placement": student.placement(),
        "lastLogin": student.last_login,
    }


@require_http_methods(["GET"])
@jwt_required
@role_required("student")
@api_view
def my_report(request):
    report = analytics.student_report(request.user, _days(request))
    return JsonResponse({"student": _student_dict(request.user), **report})


@require_http_methods(["GET"])
@jwt_required
@role_required(*STAFF)
@api_view
def student_report(request, student_id):
    try:
        student = (
            User.objects.select_related(*User.PLACEMENT_FIELDS)
            .filter(institution=request.user.institution, role="student", pk=student_id)
            .first()
        )
    except ValidationError:  # not a valid ObjectId
        student = None
    if student is None:
        return error("Student not found", 404)
    report = analytics.student_report(student, _days(request))
    return JsonResponse({"student": _student_dict(student), **report})


@require_http_methods(["GET"])
@jwt_required
@role_required(*STAFF)
@api_view
def overview(request):
    """?batch=&department=&section=&cohort= narrows the report to one group (the deepest given)."""
    institution = request.user.institution
    days = _days(request)
    students = structure.filter_by_groups(User.objects.filter(institution=institution), institution, request.GET)
    scope = None
    for level in reversed(LEVELS):
        if request.GET.get(level, "").strip():
            scope = structure.find_node(institution, level, request.GET[level])
            break
    return JsonResponse(analytics.overview(institution, students, scope, days))
