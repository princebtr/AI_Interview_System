import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from config.http import BadRequest

_STRONG = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)")


def _text(data, key):
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def clean_name(data, errors):
    name = _text(data, "name")
    if not name:
        errors.append({"field": "name", "message": "Name is required"})
    elif not 2 <= len(name) <= 50:
        errors.append({"field": "name", "message": "Name must be 2-50 characters"})
    return name


def clean_email(data, errors):
    email = _text(data, "email").lower()
    try:
        validate_email(email)
    except ValidationError:
        errors.append({"field": "email", "message": "Please provide a valid email"})
    return email


def clean_new_password(value, errors, field="password"):
    if not isinstance(value, str) or len(value) < 6:
        errors.append({"field": field, "message": "Password must be at least 6 characters"})
    elif len(value.encode()) > 72:
        errors.append({"field": field, "message": "Password must be at most 72 bytes"})
    elif not _STRONG.match(value):
        errors.append(
            {
                "field": field,
                "message": "Password must contain a lowercase letter, an uppercase letter and a number",
            }
        )
    return value


def raise_if(errors):
    if errors:
        raise BadRequest(errors[0]["message"], errors)
