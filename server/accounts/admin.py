"""Django admin (/admin) for platform staff: every institution's accounts, for
support work such as resetting a password or unlocking a throttled sign-in.
Institutions manage their own people in the app; this is the fallback."""
from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html, format_html_join

from institutions.models import AuditLog

from . import validators
from .models import User
from .passwords import generate_password
from .throttle import clear_attempts, throttle_key


class UserAdminForm(forms.ModelForm):
    temporary_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="New accounts only. Leave blank to generate one; it's shown once after saving.",
    )

    class Meta:
        model = User
        fields = ["name", "email", "role", "institution", "cohort", "is_email_verified"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(f"An account with {email} already exists.")
        return email

    def clean_temporary_password(self):
        password = self.cleaned_data.get("temporary_password") or ""
        if password:
            errors = []
            validators.clean_new_password(password, errors)
            if errors:
                raise forms.ValidationError(errors[0]["message"])
        return password

    def clean(self):
        data = super().clean()
        institution, cohort, role = data.get("institution"), data.get("cohort"), data.get("role")
        if not institution:
            self.add_error("institution", "Every account belongs to an institution.")
        if role == "student":
            if not cohort:
                self.add_error("cohort", "Students need a cohort.")
            elif institution and cohort.institution_id != institution.pk:
                self.add_error("cohort", "This cohort belongs to another institution.")
        elif cohort:
            data["cohort"] = None  # staff have no cohort
        return data


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    list_display = ["name", "email", "role", "institution", "cohort", "status", "last_login"]
    list_filter = ["role", "institution", "must_change_password"]
    search_fields = ["name", "email"]
    list_select_related = ["institution", "cohort"]
    readonly_fields = ["status", "last_login", "created_at", "updated_at"]
    actions = ["reset_password", "sign_out_everywhere", "unlock_sign_in"]

    def get_fieldsets(self, request, obj=None):
        account = ["name", "email", "role", "institution", "cohort", "is_email_verified"]
        if obj is None:
            return [(None, {"fields": account + ["temporary_password"]})]
        return [
            (None, {"fields": account}),
            ("Sign-in", {"fields": ["status", "last_login", "created_at", "updated_at"]}),
        ]

    @admin.display(description="Status")
    def status(self, obj):
        if obj.must_change_password:
            return "Must set a password"
        return "Active" if obj.last_login else "Not signed in yet"

    def save_model(self, request, obj, form, change):
        if change:
            if "email" in form.changed_data or "role" in form.changed_data:
                obj.token_version += 1  # sign them out: their tokens describe the old account
            super().save_model(request, obj, form, change)
            return
        password = form.cleaned_data["temporary_password"] or generate_password()
        obj.set_password(password)
        obj.must_change_password = True
        super().save_model(request, obj, form, change)
        AuditLog.record(obj.institution, None, "user.created", f"Platform staff added {obj.name} ({obj.role})")
        if not form.cleaned_data["temporary_password"]:
            self.message_user(
                request,
                format_html("Temporary password for {}: <code>{}</code> (shown only once).", obj.email, password),
                messages.SUCCESS,
            )

    @admin.action(description="Reset password (generate a temporary one)")
    def reset_password(self, request, queryset):
        rows = []
        for user in queryset:
            password = generate_password()
            user.set_password(password)
            user.must_change_password = True
            user.token_version += 1
            user.save(update_fields=["password", "must_change_password", "token_version", "updated_at"])
            clear_attempts(throttle_key("login", user.email))
            if user.institution_id:
                AuditLog.record(user.institution, None, "user.password_reset", f"Platform staff reset the password for {user.name}")
            rows.append((user.email, password))
        self.message_user(
            request,
            format_html(
                "New temporary passwords (shown only once; they choose their own at sign-in):<br>{}",
                format_html_join(format_html("<br>"), "{}: <code>{}</code>", rows),
            ),
            messages.SUCCESS,
        )

    @admin.action(description="Sign out of every device")
    def sign_out_everywhere(self, request, queryset):
        for user in queryset:
            user.token_version += 1
            user.save(update_fields=["token_version", "updated_at"])
        self.message_user(request, f"Signed out {queryset.count()} account(s) everywhere.", messages.SUCCESS)

    @admin.action(description="Unlock sign-in (clear failed attempts)")
    def unlock_sign_in(self, request, queryset):
        for user in queryset:
            clear_attempts(throttle_key("login", user.email))
        self.message_user(request, f"Cleared failed sign-in attempts for {queryset.count()} account(s).", messages.SUCCESS)
