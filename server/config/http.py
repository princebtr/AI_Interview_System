"""Small JSON helpers shared by every app's views."""
import json
import unicodedata

from django.http import JsonResponse


class BadRequest(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.message = message
        self.errors = errors


def error(message, status=400, **extra):
    return JsonResponse({"success": False, "message": message, "error": message, **extra}, status=status)


def json_body(request):
    # Requiring the JSON content type means browsers must send a CORS
    # preflight, so other sites can't post forms that parse as JSON.
    if request.body and request.content_type != "application/json":
        raise BadRequest("Send the request body as JSON (Content-Type: application/json)")
    try:
        data = json.loads(request.body or b"{}")
        # Lone surrogates ("\ud800") parse but can't be stored or hashed.
        json.dumps(data, ensure_ascii=False).encode("utf-8")
    except (ValueError, RecursionError):  # includes UnicodeDecodeError/UnicodeEncodeError
        raise BadRequest("Invalid JSON body")
    if not isinstance(data, dict):
        raise BadRequest("JSON body must be an object")
    return data


def clean_query(value, limit=100):
    """A trimmed search string from the query string. Control characters (NUL
    etc.) are rejected: MongoDB refuses them in patterns, and silently dropping
    them would search for something the user didn't ask for."""
    value = (value or "").strip()
    if any(unicodedata.category(ch) == "Cc" for ch in value):
        raise BadRequest("Search text contains characters that aren't allowed")
    return value[:limit]


def api_view(view):
    """Turn BadRequest into a 400 JSON response."""
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except BadRequest as exc:
            extra = {"errors": exc.errors} if exc.errors else {}
            return error(exc.message, 400, **extra)

    return wrapper
