"""Notes and messages: staff post to a batch, department, section or cohort,
and every student beneath it can read the post and its attachments."""
from django.db import models
from django.utils import timezone

from institutions.models import Audience


class Post(Audience):
    KIND_CHOICES = [("message", "Message"), ("note", "Note")]

    institution = models.ForeignKey(
        "institutions.Institution", on_delete=models.CASCADE, related_name="posts"
    )
    author = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="posts"
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="message")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    pinned = models.BooleanField(default=False)
    comments_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)  # last change to title, body or files

    class Meta:
        ordering = ["-pinned", "-created_at"]

    def __str__(self):
        return self.title


class Attachment(models.Model):
    """A file shared with a post. Stored in the database (like institution
    logos), so it's covered by the same backups and tenant scoping."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="attachments")
    name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=100)  # from the extension, never the browser
    size = models.PositiveIntegerField()
    data = models.BinaryField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def to_dict(self):
        return {"id": str(self.pk), "name": self.name, "contentType": self.content_type, "size": self.size}


class PostRead(models.Model):
    """A student has opened a post (once per student)."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["post", "user"], name="one_read_per_student")]


class Comment(models.Model):
    """A comment on a post, by a student in its audience or a staff member."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]


class Reaction(models.Model):
    """One person's reaction of one kind to a post (each kind at most once per person)."""

    KINDS = ("like", "love", "celebrate", "insightful", "curious", "thanks")

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "user", "kind"], name="one_reaction_per_kind_per_user")
        ]
