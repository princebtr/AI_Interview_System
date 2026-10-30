import os
from pathlib import Path

import django_mongodb_backend
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_list(name, default=""):
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "insecure-dev-only-key"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DEBUG is off")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "config.mongo_apps.MongoAdminConfig",  # /admin: Django's admin site (platform staff)
    "config.mongo_apps.MongoAuthConfig",
    "config.mongo_apps.MongoContentTypesConfig",
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "corsheaders",
    "institutions.apps.InstitutionsConfig",
    "accounts.apps.AccountsConfig",
    "ai.apps.AiConfig",
    "assessments.apps.AssessmentsConfig",
    "board.apps.BoardConfig",
    "reports.apps.ReportsConfig",
]

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# MongoDB
DATABASES = {
    "default": django_mongodb_backend.parse_uri(
        os.getenv("MONGODB_URI", "mongodb://localhost:27017/ai_interview_system"),
        db_name=os.getenv("MONGODB_NAME", "ai_interview_system"),
    ),
}
DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"
# ObjectId versions of the contrib apps' migrations (see config/mongo_apps.py).
MIGRATION_MODULES = {
    "admin": "mongo_migrations.admin",
    "auth": "mongo_migrations.auth",
    "contenttypes": "mongo_migrations.contenttypes",
}

# Where users sign in; printed by the onboarding command.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# CORS (React dev server)
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173"
)
CORS_ALLOW_CREDENTIALS = False  # the API authenticates with Bearer tokens, not cookies

# Auth
JWT_SECRET = os.getenv("JWT_SECRET") or SECRET_KEY
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
MAX_LOGIN_ATTEMPTS = 5  # password checks per email (or per user for password changes)...
LOGIN_WINDOW_MINUTES = 15  # ...within this sliding window
BCRYPT_ROUNDS = 12

# AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Google retires Gemini models regularly; when one goes away, change GEMINI_MODEL.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODELS = env_list("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash-lite")
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "50"))


def _env_float(name, default):
    return float(os.getenv(name, default))


def _env_int(name, default):
    return int(os.getenv(name, default))


# Proctoring detection (ai/vision.py, ai/detection.py; tuning guide in README).
# Models live in server/models/: run `python manage.py fetch_proctoring_models`.
# Thresholds were chosen on labelled COCO 2017 images (see README for numbers).
PROCTORING = {
    # One YOLO pass finds people, phones and phone look-alikes; YuNet finds faces.
    "OBJECT_MODEL": BASE_DIR / "models" / os.getenv("PROCTOR_OBJECT_MODEL", "yolo11m.pt"),
    "FACE_MODEL": BASE_DIR / "models" / os.getenv("PROCTOR_FACE_MODEL", "face_detection_yunet_2023mar.onnx"),
    "INFERENCE_SIZE": _env_int("PROCTOR_INFERENCE_SIZE", 640),
    # Per-frame confidence thresholds (0-1).
    "PERSON_CONFIDENCE": _env_float("PROCTOR_PERSON_CONFIDENCE", 0.5),
    "FACE_CONFIDENCE": _env_float("PROCTOR_FACE_CONFIDENCE", 0.6),  # a face counts as visible
    "FACE_RESCUE_CONFIDENCE": _env_float("PROCTOR_FACE_RESCUE_CONFIDENCE", 0.8),  # a face alone proves presence
    "PHONE_SUSPECT_CONFIDENCE": _env_float("PROCTOR_PHONE_SUSPECT_CONFIDENCE", 0.25),  # "Phone suspected"
    "PHONE_CONFIDENCE": _env_float("PROCTOR_PHONE_CONFIDENCE", 0.35),  # counts as evidence
    "LOOKALIKE_IOU": _env_float("PROCTOR_LOOKALIKE_IOU", 0.5),  # phone box on a likelier book/remote/laptop
    "LOOK_AWAY_YAW": _env_float("PROCTOR_LOOK_AWAY_YAW", 0.6),  # nose offset / eye distance; status only
    # Browser timing (milliseconds) and evidence windows. A violation needs at least
    # `positives` matching frames among the frames of the last `window` ms, then
    # waits `cooldown` ms (or for the problem to clear) before it can count again.
    "FRAME_INTERVAL_MS": _env_int("PROCTOR_FRAME_INTERVAL_MS", 2000),
    "MIN_SERVER_INTERVAL_MS": _env_int("PROCTOR_MIN_SERVER_INTERVAL_MS", 1000),
    "ABSENCE": {"window": _env_int("PROCTOR_ABSENCE_WINDOW_MS", 12000), "positives": _env_int("PROCTOR_ABSENCE_FRAMES", 5)},
    "MULTIPLE": {"window": _env_int("PROCTOR_MULTIPLE_WINDOW_MS", 10000), "positives": _env_int("PROCTOR_MULTIPLE_FRAMES", 4)},
    "PHONE": {"window": _env_int("PROCTOR_PHONE_WINDOW_MS", 10000), "positives": _env_int("PROCTOR_PHONE_FRAMES", 3)},
    "CLEAR_RATIO": _env_float("PROCTOR_CLEAR_RATIO", 0.2),  # below this share the incident is over
    "COOLDOWN_MS": _env_int("PROCTOR_COOLDOWN_MS", 60000),
    "CAMERA_GRACE_MS": _env_int("PROCTOR_CAMERA_GRACE_MS", 30000),
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

MEDIA_ROOT = BASE_DIR / "media"
STATIC_URL = "static/"  # required by django.contrib.staticfiles

# No CSRF middleware: the API authenticates with Bearer tokens (never cookies),
# so cross-site requests can't act as a signed-in user. With it, every POST from
# the React app (login included) fails with 403.

# Production hardening
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True

USE_TZ = True
TIME_ZONE = "UTC"
APPEND_SLASH = False
