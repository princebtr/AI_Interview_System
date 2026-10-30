"""Django admin (/admin) for platform staff: a read-only view of every
institution's notes and messages, for support questions. Staff post in the app."""
from django.contrib import admin

from assessments.admin import ReadOnlyAdmin

from .models import Post


@admin.register(Post)
class PostAdmin(ReadOnlyAdmin):
    list_display = ["title", "kind", "institution", "audience_label", "author", "pinned", "created_at"]
    list_filter = ["kind", "institution"]
    search_fields = ["title", "body"]
    date_hierarchy = "created_at"
    list_select_related = ["institution", *Post.AUDIENCE_FIELDS, "author"]

    @admin.display(description="Shared with")
    def audience_label(self, obj):
        return obj.audience_dict()["label"]
