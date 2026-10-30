from django.db import IntegrityError
from django.db.models import F
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from config.http import api_view, error, json_body

from . import validators as v
from .auth import allow_pending_password, jwt_required, token_response
from .models import User
from .throttle import clear_attempts, reserve_attempt, throttle_key


def too_many_attempts(wait_seconds):
    minutes = max(1, -(-wait_seconds // 60))
    response = error(
        f"Too many attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.", 429
    )
    response["Retry-After"] = str(wait_seconds)
    return response


@require_http_methods(["POST"])
@api_view
def login(request):
    data = json_body(request)
    email = data.get("email")
    password = data.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or not email or not password:
        return error("Please provide an email and password", 400)
    email = email.strip().lower()

    # Throttle by email whether or not an account exists, so responses (and
    # timing) never reveal which emails are registered.
    key = throttle_key("login", email)
    wait = reserve_attempt(key)
    if wait:
        return too_many_attempts(wait)

    user = (
        User.objects.select_related("institution", *User.PLACEMENT_FIELDS)
        .defer("institution__logo")
        .filter(email=email)
        .first()
    )
    if user is None:
        User.burn_password_check(password)
        return error("Invalid credentials", 401)
    if not user.check_password(password):
        return error("Invalid credentials", 401)

    clear_attempts(key)
    if not user.has_active_institution:
        return error(
            "Your account isn't linked to an active institution. Contact your administrator.",
            403,
        )
    user.register_successful_login()
    return token_response(user)


@require_http_methods(["GET", "POST"])
def logout(request):
    # Tokens live in the client, which discards its copy. Changing the
    # password (or an admin reset) revokes every session server-side.
    return JsonResponse({"success": True, "message": "User logged out successfully"})


@require_http_methods(["POST"])
@jwt_required
@allow_pending_password
def logout_all(request):
    """Revoke every session of this account, this one included (e.g. a lost laptop)."""
    User.objects.filter(pk=request.user.pk).update(token_version=F("token_version") + 1)
    return JsonResponse({"success": True, "message": "Signed out on every device"})


@require_http_methods(["GET"])
@jwt_required
@allow_pending_password
def me(request):
    return JsonResponse({"success": True, "user": request.user.to_dict()})


@require_http_methods(["PUT"])
@jwt_required
@api_view
def update_details(request):
    data = json_body(request)
    user = request.user
    errors = []
    name = v.clean_name(data, errors) if "name" in data else user.name
    email = v.clean_email(data, errors) if "email" in data else user.email
    v.raise_if(errors)

    if email != user.email and User.objects.filter(email=email).exclude(pk=user.pk).exists():
        return error("Email already exists", 400)

    user.name, user.email = name, email
    try:
        user.save(update_fields=["name", "email", "updated_at"])
    except IntegrityError:
        return error("Email already exists", 400)
    return JsonResponse({"success": True, "user": user.to_dict()})


@require_http_methods(["PUT"])
@jwt_required
@allow_pending_password
@api_view
def update_password(request):
    data = json_body(request)
    user = request.user
    current = data.get("currentPassword")
    if not isinstance(current, str) or not current:
        return error("Current password is incorrect", 400)

    key = throttle_key("password", user.pk)
    wait = reserve_attempt(key)
    if wait:
        return too_many_attempts(wait)
    if not user.check_password(current):
        return error("Current password is incorrect", 400)
    clear_attempts(key)

    errors = []
    new_password = v.clean_new_password(data.get("newPassword"), errors, "newPassword")
    if not errors and new_password == current:
        errors.append({"field": "newPassword", "message": "Choose a password different from your current one"})
    v.raise_if(errors)

    user.set_password(new_password)
    user.must_change_password = False
    user.token_version += 1  # sign out every other session, including temporary-password ones
    user.save(update_fields=["password", "must_change_password", "token_version", "updated_at"])
    return token_response(user)
