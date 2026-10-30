from django.db import models
from django.db.models import Q

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


# --------------------------------------------------------------------------- #
# Academic structure: Batch -> Department -> Section -> Cohort                 #
# --------------------------------------------------------------------------- #
# Each level is a tree node owned by one institution. Names are unique within
# their parent, so "CSE" can exist under both the 2026 and 2027 batches. Every
# student sits in exactly one cohort and also stores the cohort's ancestors
# (see User.place), so filtering by any level is a single indexed match.


class StructureNode(models.Model):
    LEVEL = None  # "batch" | "department" | "section" | "cohort"
    PARENT_FIELD = None  # name of the FK to the level above (None for batches)

    name = models.CharField(max_length=60)
    # Case- and whitespace-insensitive form of `name`; unique within the parent
    # so "CSE 2027" and "cse  2027" can't coexist, even under concurrent requests.
    name_key = models.CharField(max_length=60, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["name_key"]

    @staticmethod
    def clean_name(name):
        return " ".join(name.split())

    @classmethod
    def key_for(cls, name):
        return cls.clean_name(name).casefold()

    def save(self, *args, **kwargs):
        self.name = self.clean_name(self.name)
        self.name_key = self.key_for(self.name)
        if kwargs.get("update_fields") and "name" in kwargs["update_fields"]:
            kwargs["update_fields"] = {*kwargs["update_fields"], "name_key"}
        super().save(*args, **kwargs)

    def __str__(self):
        return self.label

    @property
    def parent(self):
        return getattr(self, self.PARENT_FIELD) if self.PARENT_FIELD else None

    def lineage(self):
        """[batch, department, ...] down to and including this node."""
        chain, node = [], self
        while node is not None:
            chain.append(node)
            node = node.parent
        return chain[::-1]

    @property
    def label(self):
        return " · ".join(n.name for n in self.lineage())

    def to_dict(self):
        return {"id": str(self.pk), "name": self.name}

    def node_dict(self):
        """This node with its place in the tree, e.g. for a test's audience."""
        return path_dict(self.lineage())


def path_dict(lineage):
    """{level, id, name, label, path} for the last node of [batch, ..., node]."""
    node = lineage[-1]
    return {
        "level": node.LEVEL,
        "id": str(node.pk),
        "name": node.name,
        "label": " · ".join(n.name for n in lineage),
        "path": [{"level": n.LEVEL, "id": str(n.pk), "name": n.name} for n in lineage],
    }


class Batch(StructureNode):
    """Students admitted together, e.g. "2023-2027"."""

    LEVEL = "batch"

    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="batches")

    class Meta(StructureNode.Meta):
        constraints = [
            models.UniqueConstraint(fields=["institution", "name_key"], name="unique_batch_per_institution")
        ]


class Department(StructureNode):
    """A department within a batch, e.g. "Computer Science"."""

    LEVEL = "department"
    PARENT_FIELD = "batch"

    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="departments")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="departments")

    class Meta(StructureNode.Meta):
        constraints = [
            models.UniqueConstraint(fields=["batch", "name_key"], name="unique_department_per_batch")
        ]


class Section(StructureNode):
    """A class section within a department, e.g. "A"."""

    LEVEL = "section"
    PARENT_FIELD = "department"

    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="sections")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="sections")

    class Meta(StructureNode.Meta):
        constraints = [
            models.UniqueConstraint(fields=["department", "name_key"], name="unique_section_per_department")
        ]


class Cohort(StructureNode):
    """The smallest group of students, e.g. a lab group within a section."""

    LEVEL = "cohort"
    PARENT_FIELD = "section"

    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="cohorts")
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="cohorts")

    class Meta(StructureNode.Meta):
        constraints = [
            models.UniqueConstraint(fields=["section", "name_key"], name="unique_cohort_per_section")
        ]


LEVELS = ("batch", "department", "section", "cohort")
MODELS = {model.LEVEL: model for model in (Batch, Department, Section, Cohort)}
LEVEL_LABELS = {"batch": "Batch", "department": "Department", "section": "Section", "cohort": "Cohort"}
# select_related() path from a node to all of its ancestors.
ANCESTORS = {
    "batch": [],
    "department": ["batch"],
    "section": ["department__batch"],
    "cohort": ["section__department__batch"],
}


class Audience(models.Model):
    """Something assigned to one group of students: a batch, department,
    section or cohort, and so everyone beneath it (a test, a post...).

    The audience is the deepest of the four fields that is set; the ones above
    it are its ancestors, so a student's items are found with one query
    (for_student) and a group's with one match (audience_filter-style lookups).
    """

    AUDIENCE_FIELDS = LEVELS

    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="%(class)ss")
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.PROTECT, related_name="%(class)ss"
    )
    section = models.ForeignKey(Section, null=True, blank=True, on_delete=models.PROTECT, related_name="%(class)ss")
    cohort = models.ForeignKey(Cohort, null=True, blank=True, on_delete=models.PROTECT, related_name="%(class)ss")

    class Meta:
        abstract = True

    @classmethod
    def for_student(cls, user):
        """Items whose audience includes `user` (none if they aren't placed)."""
        if not user.cohort_id:
            return cls.objects.none()
        return cls.objects.filter(
            Q(cohort_id=user.cohort_id)
            | Q(cohort=None, section_id=user.section_id)
            | Q(section=None, department_id=user.department_id)
            | Q(department=None, batch_id=user.batch_id),
            institution_id=user.institution_id,
        )

    def set_audience(self, node):
        """Assign this to `node` (a Batch, Department, Section or Cohort)."""
        chain = {n.LEVEL: n for n in node.lineage()}
        for field in self.AUDIENCE_FIELDS:
            setattr(self, field, chain.get(field))

    def _audience_chain(self):
        return [getattr(self, f) for f in self.AUDIENCE_FIELDS if getattr(self, f"{f}_id")]

    @property
    def audience(self):
        """The group this is assigned to."""
        return self._audience_chain()[-1]

    @property
    def audience_level(self):
        return next(f for f in reversed(self.AUDIENCE_FIELDS) if getattr(self, f"{f}_id"))

    def audience_dict(self):
        """{level, id, name, label, path}; select_related(*AUDIENCE_FIELDS) avoids queries."""
        return path_dict(self._audience_chain())

    def audience_filter(self):
        """User.objects.filter(**this) selects the students in the audience."""
        level = self.audience_level
        return {f"{level}_id": getattr(self, f"{level}_id")}

    def audience_key(self):
        """(level, pk) of the audience, as used by ai.stats.group_stats."""
        level = self.audience_level
        return level, getattr(self, f"{level}_id")


class AuditLog(models.Model):
    """Append-only record of administrative actions (no update or delete API).

    `summary` is rendered when the event happens, so the feed still reads
    correctly if the people or groups involved are later renamed or removed.
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
