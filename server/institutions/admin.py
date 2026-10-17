"""Django admin (/admin) for platform staff: onboarding institutions with their
first admin, each institution's logo and theme colours (used by every portal and
its sign-in page), cohorts, and the audit trail."""
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from accounts import validators
from accounts.models import User
from accounts.passwords import generate_password
from config.http import BadRequest

from .branding import process_logo
from .management.commands.onboard_institution import default_academic_year
from .models import AuditLog, Cohort, Institution
from .theme import palette

DEFAULT_PRIMARY, DEFAULT_SECONDARY = "#4f46e5", "#7c3aed"  # Cohortix indigo -> violet


class ColorInput(forms.TextInput):
    input_type = "color"


class InstitutionAdminForm(forms.ModelForm):
    logo_file = forms.ImageField(
        required=False,
        label="Logo",
        help_text="PNG, JPG or WebP, up to 2 MB. Stored as a 256 px PNG.",
    )
    remove_logo = forms.BooleanField(required=False, label="Remove the current logo")
    use_default_theme = forms.BooleanField(
        required=False,
        label="Use Cohortix's default colours",
        help_text="Each role then keeps its own colour (admins blue, educators green, students violet).",
    )

    class Meta:
        model = Institution
        fields = ["name", "slug", "type", "website", "address", "academic_year", "is_active", "primary_color", "secondary_color"]
        widgets = {"primary_color": ColorInput, "secondary_color": ColorInput}
        help_texts = {
            "primary_color": "Buttons, links, highlights and the sidebar for admins, educators and students.",
            "secondary_color": "Supporting accents: badges, secondary highlights and chart series. "
            "Text on either colour switches to dark automatically when the colour is light.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        themed = bool(self.instance.pk and self.instance.primary_color)
        self.fields["use_default_theme"].initial = not themed
        # A colour input always has a value: start from the current colours or the defaults.
        if not self.instance.primary_color:
            self.initial["primary_color"] = DEFAULT_PRIMARY
        if not self.instance.secondary_color:
            self.initial["secondary_color"] = DEFAULT_SECONDARY

    def clean_primary_color(self):
        return (self.cleaned_data.get("primary_color") or "").lower()

    def clean_secondary_color(self):
        return (self.cleaned_data.get("secondary_color") or "").lower()

    def clean_logo_file(self):
        upload = self.cleaned_data.get("logo_file")
        if not upload:
            return None
        upload.seek(0)
        try:
            return process_logo(upload)
        except BadRequest as problem:
            raise forms.ValidationError(str(problem))

    def save(self, commit=True):
        institution = super().save(commit=False)
        if self.cleaned_data.get("use_default_theme"):
            institution.primary_color = institution.secondary_color = ""
        logo = self.cleaned_data.get("logo_file")
        if logo:
            institution.logo, institution.logo_version = logo
        elif self.cleaned_data.get("remove_logo"):
            institution.logo, institution.logo_version = None, ""
        if commit:
            institution.save()
        return institution


def _first_error(check, *args):
    errors = []
    check(*args, errors)
    return errors[0]["message"] if errors else None


class OnboardInstitutionForm(InstitutionAdminForm):
    """Adding an institution also creates its first admin, who gets a temporary
    password and must choose their own at first sign-in."""

    admin_name = forms.CharField(label="Admin's full name", max_length=50)
    admin_email = forms.EmailField(label="Admin's email")
    admin_password = forms.CharField(
        label="Temporary password",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to generate one. It's shown once after saving.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault("academic_year", default_academic_year())

    def clean_admin_name(self):
        name = " ".join(self.cleaned_data["admin_name"].split())
        error = _first_error(validators.clean_name, {"name": name})
        if error:
            raise forms.ValidationError(error)
        return name

    def clean_admin_email(self):
        email = self.cleaned_data["admin_email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(f"An account with {email} already exists.")
        return email

    def clean_admin_password(self):
        password = self.cleaned_data.get("admin_password") or ""
        if password:
            error = _first_error(validators.clean_new_password, password)
            if error:
                raise forms.ValidationError(error)
        return password


class CohortInline(admin.TabularInline):
    model = Cohort
    fields = ["name", "student_count", "created_at"]
    readonly_fields = ["student_count", "created_at"]
    extra = 0

    @admin.display(description="Students")
    def student_count(self, obj):
        return obj.students.count() if obj.pk else "—"


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    form = InstitutionAdminForm
    list_display = ["name", "slug", "type", "logo_thumbnail", "theme_swatches", "people", "is_active"]
    list_filter = ["type", "is_active"]
    search_fields = ["name", "slug"]
    readonly_fields = ["logo_preview", "theme_preview", "people", "admin_accounts", "sign_in_link", "created_at", "updated_at"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [CohortInline]
    actions = ["activate", "deactivate"]
    onboarding_fieldsets = [
        (None, {"fields": ["name", "slug", "type", "is_active"]}),
        ("Details", {"fields": ["website", "address", "academic_year"]}),
        ("First admin", {"fields": ["admin_name", "admin_email", "admin_password"]}),
        ("Logo", {"fields": ["logo_file"]}),
        ("Theme", {"fields": ["use_default_theme", "primary_color", "secondary_color"]}),
    ]
    fieldsets = [
        (None, {"fields": ["name", "slug", "type", "is_active"]}),
        ("Details", {"fields": ["website", "address", "academic_year", "sign_in_link"]}),
        ("People", {"fields": ["people", "admin_accounts"]}),
        ("Logo", {"fields": ["logo_preview", "logo_file", "remove_logo"]}),
        ("Theme", {"fields": ["use_default_theme", "primary_color", "secondary_color", "theme_preview"]}),
        ("Record", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).defer("logo")

    # --- onboarding ------------------------------------------------------
    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = OnboardInstitutionForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        return self.onboarding_fieldsets if obj is None else self.fieldsets

    def get_inlines(self, request, obj):
        return self.inlines if obj else []

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            AuditLog.record(obj, None, "institution.updated", f"Platform staff updated {obj.name}")
            return

        password = form.cleaned_data["admin_password"] or generate_password()
        admin_user = User(
            email=form.cleaned_data["admin_email"],
            name=form.cleaned_data["admin_name"],
            role="admin",
            must_change_password=True,
        )
        admin_user.set_password(password)  # hash before writing anything
        super().save_model(request, obj, form, change)
        try:
            admin_user.institution = obj
            admin_user.save()
            AuditLog.record(obj, None, "institution.onboarded", f"{obj.name} joined, with {admin_user.name} as the first admin")
        except BaseException:
            # No multi-document transactions on this backend: undo by hand.
            if admin_user.pk:
                User.objects.filter(pk=admin_user.pk).delete()
            obj.delete()
            raise

        generated = not form.cleaned_data["admin_password"]
        self.message_user(
            request,
            format_html(
                "Onboarded {}. First admin: {} &lt;{}&gt;{}. Sign-in page: {} . Share these over a secure "
                "channel; the admin chooses their own password at first sign-in.",
                obj.name,
                admin_user.name,
                admin_user.email,
                format_html(", temporary password <code>{}</code> (shown only once)", password) if generated else "",
                self._sign_in_url(obj),
            ),
            messages.SUCCESS,
        )

    # --- people ----------------------------------------------------------
    @staticmethod
    def _sign_in_url(obj):
        return f"{settings.FRONTEND_URL.rstrip('/')}/login?school={obj.slug}"

    @admin.display(description="Sign-in page")
    def sign_in_link(self, obj):
        url = self._sign_in_url(obj)
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', url, url)

    @admin.display(description="People")
    def people(self, obj):
        counts = {role: obj.users.filter(role=role).count() for role in ("admin", "educator", "student")}
        url = reverse("admin:accounts_user_changelist") + f"?institution__id__exact={obj.pk}"
        return format_html(
            '<a href="{}">{} admins · {} educators · {} students</a>',
            url, counts["admin"], counts["educator"], counts["student"],
        )

    @admin.display(description="Admin accounts")
    def admin_accounts(self, obj):
        admins = obj.users.filter(role="admin").order_by("name")
        if not admins:
            return "None: add one under Users."
        return format_html_join(
            format_html("<br>"),
            '<a href="{}">{}</a> &lt;{}&gt;',
            ((reverse("admin:accounts_user_change", args=[u.pk]), u.name, u.email) for u in admins),
        )

    @admin.action(description="Activate selected institutions")
    def activate(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} institution(s).", messages.SUCCESS)

    @admin.action(description="Deactivate selected institutions (their users can't sign in)")
    def deactivate(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} institution(s).", messages.WARNING)

    @admin.display(description="Logo")
    def logo_thumbnail(self, obj):
        return self._logo(obj, 28)

    @admin.display(description="Current logo")
    def logo_preview(self, obj):
        return self._logo(obj, 96) or "No logo yet: the app shows the institution's initials."

    @staticmethod
    def _logo(obj, size):
        if not obj.logo_url:
            return ""
        return format_html(
            '<img src="{}" alt="" style="height:{}px;width:{}px;object-fit:contain;border-radius:6px;'
            'background:#f8fafc;border:1px solid #e2e8f0">',
            obj.logo_url,
            size,
            size,
        )

    @admin.display(description="Theme")
    def theme_swatches(self, obj):
        if not obj.primary_color:
            return "Default"
        return format_html_join(
            "",
            '<span title="{}" style="display:inline-block;width:18px;height:18px;margin-right:4px;'
            'border-radius:4px;border:1px solid #cbd5e1;background:{}"></span>',
            ((c, c) for c in (obj.primary_color, obj.secondary_color or obj.primary_color)),
        )

    @admin.display(description="Preview (saved colours)")
    def theme_preview(self, obj):
        variables = palette(obj.primary_color, obj.secondary_color)
        if not variables:
            return "Default Cohortix colours for each role."
        return format_html(
            '<div style="display:flex;gap:12px;align-items:center">'
            '<span style="padding:8px 16px;border-radius:8px;background:{};color:{};font-weight:600">Primary button</span>'
            '<span style="padding:6px 12px;border-radius:999px;background:{};color:{};font-weight:600">Secondary</span>'
            '<span style="padding:6px 12px;border-radius:999px;background:{};color:{};font-weight:600">Highlight</span>'
            "</div>",
            variables["--color-primary"],
            variables["--color-on-primary"],
            variables["--color-secondary"],
            variables["--color-on-secondary"],
            variables["--color-accent-50"],
            variables["--color-accent-700"],
        )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only: the audit trail is append-only."""

    list_display = ["created_at", "institution", "actor", "action", "summary"]
    list_filter = ["institution", "action"]
    search_fields = ["summary", "action"]
    date_hierarchy = "created_at"
    list_select_related = ["institution", "actor"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
