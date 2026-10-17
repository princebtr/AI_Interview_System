"""Django admin (/admin) for platform staff: a read-only view of every
institution's scheduled tests and sittings, for support questions such as
"why was this attempt auto-submitted?". Educators manage tests in the app."""
from django.contrib import admin

from .models import Assessment, AssessmentAttempt


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Assessment)
class AssessmentAdmin(ReadOnlyAdmin):
    list_display = ["title", "institution", "cohort", "starts_at", "duration_minutes", "created_by"]
    list_filter = ["institution"]
    search_fields = ["title", "subject"]
    date_hierarchy = "starts_at"
    list_select_related = ["institution", "cohort", "created_by"]
    exclude = ["questions"]


@admin.register(AssessmentAttempt)
class AssessmentAttemptAdmin(ReadOnlyAdmin):
    list_display = [
        "assessment", "student", "started_at", "submitted_at", "score",
        "auto_submitted", "submission_reason", "screen_switch_count", "face_violation_count",
    ]
    list_filter = ["auto_submitted", "assessment__institution"]
    search_fields = ["student__email", "student__name", "assessment__title"]
    list_select_related = ["assessment", "student"]
    exclude = ["order", "answers", "review"]
