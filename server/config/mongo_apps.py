"""Django's admin, auth and contenttypes apps with MongoDB ObjectId keys.

Their stock migrations create integer ids, which MongoDB can't generate; these
configs and the migrations in mongo_migrations/ use ObjectIds instead (the
setup django-mongodb-backend documents)."""
from django.contrib.admin.apps import AdminConfig
from django.contrib.auth.apps import AuthConfig
from django.contrib.contenttypes.apps import ContentTypesConfig

OBJECT_ID = "django_mongodb_backend.fields.ObjectIdAutoField"


class MongoAdminConfig(AdminConfig):
    default_auto_field = OBJECT_ID


class MongoAuthConfig(AuthConfig):
    default_auto_field = OBJECT_ID


class MongoContentTypesConfig(ContentTypesConfig):
    default_auto_field = OBJECT_ID
