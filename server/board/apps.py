from django.apps import AppConfig


class BoardConfig(AppConfig):
    name = "board"
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
