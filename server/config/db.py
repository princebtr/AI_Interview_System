import re


def iexact(field, value):
    """Case-insensitive exact-match filter that is safe for any input.

    django-mongodb-backend passes `__iexact` values to MongoDB as an unescaped
    regex, so "CSE.2027" matches "CSE 2027" and "(" raises a DatabaseError.
    Use as: Model.objects.filter(**iexact("name", value)).
    """
    return {f"{field}__iregex": rf"^{re.escape(value)}$"}
