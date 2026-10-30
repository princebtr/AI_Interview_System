from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse

from config.http import error

from .models import User


def create_token(user):
    now = datetime.now(timezone.utc)
    payload = {
        "id": str(user.pk),
        "ver": user.token_version,
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def _extract_token(request):
    # Bearer only: the client keeps the token itself. Cookie auth would need
    # CSRF protection, since browsers attach cookies to same-site form posts.
    header = request.headers.get("Authorization", "")
    return header[7:].strip() if header.startswith("Bearer ") else None


def get_request_user(request):
    """The signed-in user, or None if the token is missing, invalid or revoked
    (password changed or reset), or their institution is gone or deactivated."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user = (
            User.objects.select_related("institution", *User.PLACEMENT_FIELDS)
            .defer("institution__logo")
            .filter(pk=payload["id"])
            .first()
        )
    except (jwt.PyJWTError, KeyError, ValueError, ValidationError):
        return None
    if user is None or payload.get("ver") != user.token_version:
        return None
    return user if user.has_active_institution else None


def allow_pending_password(view):
    """Let users who still have a temporary password reach this view."""
    view.allow_pending_password = True
    return view


def jwt_required(view):
    allow_pending = getattr(view, "allow_pending_password", False)

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = get_request_user(request)
        if user is None:
            return error("Not authorized to access this route", 401)
        if user.must_change_password and not allow_pending:
            return error(
                "Set a new password to continue", 403, code="password_change_required"
            )
        request.user = user
        return view(request, *args, **kwargs)

    return wrapper


def role_required(*roles):
    """Restrict a view to the given roles. Must sit below @jwt_required."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                return error("You don't have permission to do that", 403)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def token_response(user, status=200):
    return JsonResponse(
        {"success": True, "token": create_token(user), "user": user.to_dict()}, status=status
    )
