"""Validation shared by the onboarding command and the institution API."""
import re

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from config.db import iexact

from .models import Institution

ACADEMIC_YEAR = re.compile(r"^\d{4}-(\d{2}|\d{4})$")
MAX_NAME = 150


def clean_website(url):
    url = url.strip()
    return url if not url or "://" in url else f"https://{url}"


def website_error(url):
    try:
        URLValidator(schemes=["http", "https"])(url)
    except ValidationError:
        return "Enter a valid website URL."
    return None


def academic_year_error(value):
    return None if ACADEMIC_YEAR.match(value) else "Use the format 2026-27."


def name_error(name, exclude=None):
    if not 2 <= len(name) <= MAX_NAME:
        return f"Name must be 2-{MAX_NAME} characters."
    taken = Institution.objects.filter(**iexact("name", name))
    if exclude is not None:
        taken = taken.exclude(pk=exclude.pk)
    if taken.exists():
        return f'An institution named "{name}" already exists.'
    return None
