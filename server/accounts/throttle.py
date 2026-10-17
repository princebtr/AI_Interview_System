"""Rate-limit password guesses: at most MAX_LOGIN_ATTEMPTS checks per key in a
sliding LOGIN_WINDOW_MINUTES window.

An attempt is recorded *before* the password is checked and the count is read
back afterwards, so concurrent requests can't exceed the limit. Blocked
requests aren't recorded, so a lockout ends on its own once the window passes.
"""
import hashlib
import math
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import LoginAttempt


def throttle_key(kind, value):
    return hashlib.sha256(f"{kind}:{value}".encode("utf-8", "surrogatepass")).hexdigest()


def _window_start():
    return timezone.now() - timedelta(minutes=settings.LOGIN_WINDOW_MINUTES)


def reserve_attempt(key):
    """Record an attempt for `key`. Returns None if the caller may check the
    password, or the number of seconds to wait if the limit has been reached."""
    start = _window_start()
    LoginAttempt.objects.filter(key=key, created_at__lt=start).delete()
    recent = LoginAttempt.objects.filter(key=key, created_at__gte=start)

    if recent.count() < settings.MAX_LOGIN_ATTEMPTS:
        LoginAttempt.objects.create(key=key)
        if recent.count() <= settings.MAX_LOGIN_ATTEMPTS:
            return None

    oldest = recent.order_by("created_at").values_list("created_at", flat=True).first()
    if oldest is None:
        return 1
    wait = oldest + timedelta(minutes=settings.LOGIN_WINDOW_MINUTES) - timezone.now()
    return max(1, math.ceil(wait.total_seconds()))


def clear_attempts(key):
    LoginAttempt.objects.filter(key=key).delete()
