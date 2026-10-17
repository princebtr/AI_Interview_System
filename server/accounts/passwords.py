import secrets
import string
from concurrent.futures import ThreadPoolExecutor

import bcrypt
from django.conf import settings

# No look-alike characters (0/O, 1/l/I): temporary passwords get read aloud and retyped.
_SETS = ("ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnopqrstuvwxyz", "23456789")


def generate_password(length=14):
    """A random password with at least one upper, lower and digit."""
    alphabet = "".join(_SETS)
    chars = [secrets.choice(s) for s in _SETS]
    chars += [secrets.choice(alphabet) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def hash_password(raw):
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(raw.encode(), salt).decode()


def hash_many(passwords, workers=8):
    """bcrypt releases the GIL, so threads hash a batch several times faster."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(hash_password, passwords))
