from django.db import models

from .theme import hex_color, theme_dict


class Institution(models.Model):
    """A tenant: one school, college or university and everything it owns."""

    TYPE_CHOICES = [
        ("school", "School"),
        ("college", "College"),
        ("university", "University"),
    ]

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, unique=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    website = models.URLField(blank=True)
    address = models.TextField(blank=True)
    academic_year = models.CharField(max_length=20, blank=True)
    # Branding: a small PNG (re-encoded on upload) shown at the top of the app.
    logo = models.BinaryField(null=True, blank=True, editable=False)
    logo_version = models.CharField(max_length=16, blank=True)  # content hash, busts caches
    # Theme for every portal of this institution (blank: Cohortix's role colours).
    # Set by platform staff in the Django admin (/admin); see institutions/theme.py.
    primary_color = models.CharField(max_length=7, blank=True, validators=[hex_color])
    secondary_color = models.CharField(max_length=7, blank=True, validators=[hex_color])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def logo_url(self):
        """Public, versioned path of the logo (served by institutions.views.logo)."""
        return f"/api/institutions/{self.pk}/logo?v={self.logo_version}" if self.logo_version else None

    def to_dict(self):
        return {
            "id": str(self.pk),
            "name": self.name,
            "slug": self.slug,
            "type": self.type,
            "academicYear": self.academic_year,
            "website": self.website,
            "logoUrl": self.logo_url,
            "theme": theme_dict(self),
        }


class Cohort(models.Model):
    """A group of students who study together, e.g. "CSE-2027"."""

    institution = models.ForeignKey(
        Institution, on_delete=models.CASCADE, related_name="cohorts"
    )
    name = models.CharField(max_length=60)
    # Case- and whitespace-insensitive form of `name`; unique per institution so
    # "CSE 2027" and "cse  2027" can't coexist, even under concurrent requests.
    name_key = models.CharField(max_length=60, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "name_key"], name="unique_cohort_per_institution"
            )
        ]

    @staticmethod
    def clean_name(name):
        return " ".join(name.split())

    @classmethod
    def key_for(cls, name):
        return cls.clean_name(name).casefold()

    def save(self, *args, **kwargs):
        self.name = self.clean_name(self.name)
        self.name_key = self.key_for(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def to_dict(self):
        return {"id": str(self.pk), "name": self.name}


class AuditLog(models.Model):
    """Append-only record of administrative actions (no update or delete API).

    `summary` is rendered when the event happens, so the feed still reads
    correctly if the people or cohorts involved are later renamed or removed.
    """

    institution = models.ForeignKey(
        Institution, on_delete=models.CASCADE, related_name="audit_logs"
    )
    actor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=40)
    summary = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def record(cls, institution, actor, action, summary, **metadata):
        return cls.objects.create(
            institution=institution,
            actor=actor,
            action=action,
            summary=summary[:255],
            metadata=metadata,
        )

    def to_dict(self):
        return {
            "id": str(self.pk),
            "action": self.action,
            "summary": self.summary,
            "actor": {"id": str(self.actor_id), "name": self.actor.name} if self.actor_id else None,
            "createdAt": self.created_at,
        }
