import bcrypt
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils import timezone

_dummy_hashes = {}


def _timing_hash():
    """A hash with the configured cost factor, so checking a password for an
    unknown email takes as long as checking a real account's."""
    rounds = settings.BCRYPT_ROUNDS
    if rounds not in _dummy_hashes:
        _dummy_hashes[rounds] = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(rounds=rounds))
    return _dummy_hashes[rounds]


class User(models.Model):
    ROLE_CHOICES = [("admin", "Admin"), ("educator", "Educator"), ("student", "Student")]

    # Every account belongs to exactly one institution (tenant). It's nullable
    # only so accounts created before multi-tenancy can be migrated.
    institution = models.ForeignKey(
        "institutions.Institution",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="users",
    )
    # Students sit in one cohort of their institution and also store its
    # ancestors, so they can be found by batch, department, section or cohort
    # with one indexed match. Always set together through place(); staff have none.
    batch = models.ForeignKey(
        "institutions.Batch", null=True, blank=True, on_delete=models.PROTECT, related_name="students"
    )
    department = models.ForeignKey(
        "institutions.Department", null=True, blank=True, on_delete=models.PROTECT, related_name="students"
    )
    section = models.ForeignKey(
        "institutions.Section", null=True, blank=True, on_delete=models.PROTECT, related_name="students"
    )
    cohort = models.ForeignKey(
        "institutions.Cohort",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="students",
    )
    name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="student")
    must_change_password = models.BooleanField(default=False)
    # Embedded in every token; bumping it signs out all of the user's sessions.
    token_version = models.PositiveIntegerField(default=0)
    is_email_verified = models.BooleanField(default=False)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email

    # --- passwords -------------------------------------------------------
    def set_password(self, raw):
        from .passwords import hash_password

        self.password = hash_password(raw)

    def check_password(self, raw):
        try:
            return bcrypt.checkpw(raw.encode(), self.password.encode())
        except ValueError:  # includes un-encodable input and malformed hashes
            return False

    @staticmethod
    def burn_password_check(raw):
        """Spend the same time as check_password does for a real account."""
        try:
            bcrypt.checkpw(raw.encode()[:72], _timing_hash())
        except ValueError:
            pass

    @property
    def has_active_institution(self):
        if self.institution_id is None:
            return False
        try:
            institution = self.institution
        except ObjectDoesNotExist:  # the institution document was removed
            return False
        return institution is not None and institution.is_active

    def register_successful_login(self):
        self.last_login = timezone.now()
        self.save(update_fields=["last_login", "updated_at"])

    # --- placement in Batch -> Department -> Section -> Cohort --------------
    # select_related() these to serialise users without extra queries.
    PLACEMENT_FIELDS = ("batch", "department", "section", "cohort")

    def place(self, cohort):
        """Put the user in `cohort` (or nowhere, for None), filling in its
        section, department and batch. Doesn't save."""
        section = cohort.section if cohort else None
        department = section.department if section else None
        self.batch = department.batch if department else None
        self.department = department
        self.section = section
        self.cohort = cohort

    def placement(self):
        """{batch, department, section, cohort, label} or None when unplaced."""
        if not self.cohort_id:
            return None
        nodes = {field: getattr(self, field) for field in self.PLACEMENT_FIELDS}
        return {
            **{field: node.to_dict() if node else None for field, node in nodes.items()},
            "label": " · ".join(node.name for node in nodes.values() if node),
        }

    # --- serialisation (camelCase to match the React client) -------------
    def to_dict(self):
        return {
            "id": str(self.pk),
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "institution": self.institution.to_dict() if self.institution_id else None,
            "cohort": self.cohort.to_dict() if self.cohort_id else None,
            "placement": self.placement(),
            "mustChangePassword": self.must_change_password,
            "isEmailVerified": self.is_email_verified,
            "lastLogin": self.last_login,
            "createdAt": self.created_at,
        }


class LoginAttempt(models.Model):
    """One password check, keyed by a hash of what was being guessed (an email
    address or a user's current password). Counting these per key lets sign-in
    throttling behave identically for registered and unknown emails."""

    key = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
