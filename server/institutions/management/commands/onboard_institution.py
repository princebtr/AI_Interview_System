"""
Onboard a school, college or university: create the institution (tenant) and
its first admin account. Run by the platform operator; there is no public
sign-up.

    python manage.py onboard_institution                 # guided prompts
    python manage.py onboard_institution --no-input \\
        --name "Springfield College" --type college \\
        --admin-name "Asha Rao" --admin-email asha@springfield.edu

The admin always receives a temporary password and must replace it at first
sign-in. Leave the password blank (or omit it with --no-input) to generate one.
"""
import getpass
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify

from accounts import validators
from accounts.models import User
from accounts.passwords import generate_password
from institutions import validators as institution_rules
from institutions.models import AuditLog, Institution

TYPES = [value for value, _ in Institution.TYPE_CHOICES]
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def default_academic_year(today=None):
    """Academic years start in June: Oct 2026 -> 2026-27, Mar 2027 -> 2026-27."""
    today = today or timezone.localdate()
    start = today.year if today.month >= 6 else today.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def default_slug(name):
    """slugify() keeps underscores and may end on a hyphen after truncation;
    build a slug that always satisfies SLUG (or "" if nothing usable is left)."""
    slug = re.sub(r"[^a-z0-9]+", "-", slugify(name)).strip("-")
    return slug[:80].rstrip("-")


def first_error(check, *args):
    """Run one of the accounts validators and return its first message, if any."""
    errors = []
    check(*args, errors)
    return errors[0]["message"] if errors else None


class Command(BaseCommand):
    help = "Onboard a school or college: create the institution and its first admin."

    def add_arguments(self, parser):
        institution = parser.add_argument_group("institution")
        institution.add_argument("--name", help="Institution name")
        institution.add_argument("--type", choices=TYPES, help="Institution type")
        institution.add_argument("--slug", help="URL-safe identifier (default: from the name)")
        institution.add_argument("--website", help="Website URL (optional)")
        institution.add_argument("--address", help="Postal address (optional)")
        institution.add_argument(
            "--academic-year", dest="academic_year", help="e.g. 2026-27 (default: current)"
        )

        admin = parser.add_argument_group("first admin")
        admin.add_argument("--admin-name", dest="admin_name", help="Admin's full name")
        admin.add_argument("--admin-email", dest="admin_email", help="Admin's email")
        admin.add_argument(
            "--admin-password",
            dest="admin_password",
            help="Temporary password. Avoid on shared machines: it lands in shell history. "
            "Omit to be prompted, or to have one generated with --no-input.",
        )

        admin.add_argument(
            "--attach-existing",
            action="store_true",
            dest="attach_existing",
            help="If the admin email belongs to an account that isn't linked to any "
            "institution (created before multi-tenancy), make it this institution's admin.",
        )

        parser.add_argument(
            "--no-input",
            "--noinput",
            action="store_false",
            dest="interactive",
            help="Never prompt; fail on missing or invalid values.",
        )

    # ------------------------------------------------------------------ #
    # Prompting                                                           #
    # ------------------------------------------------------------------ #

    def ask(self, label, value=None, *, default="", required=True, validate=None, clean=None):
        """Use `value` if given and valid; otherwise prompt (interactive) or fail."""
        while True:
            if value is None:
                if self.interactive:
                    hint = f" [{default}]" if default else ("" if required else " (optional)")
                    value = input(f"  {label}{hint}: ").strip() or default
                else:
                    value = default
            value = (value or "").strip()
            if clean and value:
                value = clean(value)

            error = None
            if required and not value:
                error = f"{label} is required."
            elif value and validate:
                error = validate(value)

            if not error:
                return value
            if not self.interactive:
                raise CommandError(error)
            self.stderr.write(self.style.ERROR(f"  {error}"))
            value = None

    def ask_password(self, value):
        if value is not None:
            error = first_error(validators.clean_new_password, value)
            if error:
                raise CommandError(f"--admin-password: {error}")
            return value, False

        if not self.interactive:
            return generate_password(), True

        while True:
            value = getpass.getpass("  Temporary password (blank to generate one): ")
            if not value:
                return generate_password(), True
            error = first_error(validators.clean_new_password, value)
            if error:
                self.stderr.write(self.style.ERROR(f"  {error}"))
                continue
            if getpass.getpass("  Repeat password: ") != value:
                self.stderr.write(self.style.ERROR("  Passwords don't match."))
                continue
            return value, False

    # ------------------------------------------------------------------ #
    # Validation                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate_name(name):
        return institution_rules.name_error(name)

    @staticmethod
    def validate_type(value):
        return None if value in TYPES else f"Type must be one of: {', '.join(TYPES)}."

    @staticmethod
    def validate_slug(slug):
        if not SLUG.match(slug) or len(slug) > 80:
            return "Slug may only contain lowercase letters, numbers and single hyphens."
        if Institution.objects.filter(slug=slug).exists():
            return f'The slug "{slug}" is taken. Choose another with --slug.'
        return None

    clean_website = staticmethod(institution_rules.clean_website)
    validate_website = staticmethod(institution_rules.website_error)
    validate_academic_year = staticmethod(institution_rules.academic_year_error)

    @staticmethod
    def validate_admin_name(name):
        return first_error(validators.clean_name, {"name": name})

    def validate_admin_email(self, email):
        error = first_error(validators.clean_email, {"email": email})
        if error:
            return error
        existing = User.objects.filter(email=email).first()
        if existing is None:
            return None
        if existing.institution_id is not None:
            return f"An account with {email} already exists."
        # An account from before multi-tenancy: it can be adopted as this admin.
        if self.attach_existing or (
            self.interactive
            and input(
                f"  {email} has an account that isn't linked to any institution.\n"
                "  Make it this institution's admin? [y/N]: "
            ).strip().lower()
            in ("y", "yes")
        ):
            self.existing_admin = existing
            return None
        return (
            f"{email} has an account that isn't linked to any institution. "
            "Re-run with --attach-existing to make it this institution's admin."
        )

    # ------------------------------------------------------------------ #

    def handle(self, *args, **opts):
        self.interactive = opts["interactive"]
        self.attach_existing = opts["attach_existing"]
        self.existing_admin = None
        out = self.stdout

        if self.interactive:
            out.write(self.style.MIGRATE_HEADING("\nOnboard a new institution\n"))
            out.write("Institution")

        name = self.ask("Name", opts["name"], validate=self.validate_name)
        inst_type = self.ask(
            f"Type ({'/'.join(TYPES)})",
            opts["type"],
            validate=self.validate_type,
            clean=str.lower,
        )
        suggested_slug = default_slug(name)
        if not suggested_slug and opts["slug"] is None and not self.interactive:
            raise CommandError(
                "Couldn't make a slug from that name. Pass one with --slug "
                "(lowercase letters, numbers and hyphens)."
            )
        slug = self.ask("Slug", opts["slug"], default=suggested_slug, validate=self.validate_slug)
        website = self.ask(
            "Website",
            opts["website"],
            required=False,
            clean=self.clean_website,
            validate=self.validate_website,
        )
        address = self.ask("Address", opts["address"], required=False)
        academic_year = self.ask(
            "Academic year",
            opts["academic_year"],
            default=default_academic_year(),
            validate=self.validate_academic_year,
        )

        if self.interactive:
            out.write("\nFirst admin")
        admin_name = self.ask("Full name", opts["admin_name"], validate=self.validate_admin_name)
        admin_email = self.ask(
            "Email",
            opts["admin_email"],
            clean=str.lower,
            validate=self.validate_admin_email,
        )
        password, generated = self.ask_password(opts["admin_password"])

        if self.interactive:
            out.write("\nAbout to create:")
            out.write(f"  {name} ({inst_type}, {academic_year}), slug '{slug}'")
            adopting = " (existing account)" if self.existing_admin else ""
            out.write(f"  Admin: {admin_name} <{admin_email}>{adopting}")
            if input("\nCreate this institution? [y/N]: ").strip().lower() not in ("y", "yes"):
                raise CommandError("Cancelled. Nothing was created.")

        # Do the slow, failure-prone work (hashing) before writing anything.
        admin = self.existing_admin or User(email=admin_email)
        admin.name = admin_name
        admin.role = "admin"
        admin.cohort = None
        admin.must_change_password = True
        admin.set_password(password)
        if self.existing_admin:
            admin.token_version += 1  # sign out any old sessions

        institution = Institution.objects.create(
            name=name,
            slug=slug,
            type=inst_type,
            website=website,
            address=address,
            academic_year=academic_year,
        )
        try:
            admin.institution = institution
            admin.save()
            AuditLog.record(
                institution,
                None,
                "institution.onboarded",
                f"{institution.name} joined, with {admin.name} as the first admin",
            )
        except BaseException:
            # No multi-document transactions on this backend, and Ctrl-C must not
            # leave an institution without an admin: undo by hand, then re-raise.
            if self.existing_admin:
                User.objects.filter(pk=admin.pk).update(institution=None, role="student")
            elif admin.pk:
                User.objects.filter(pk=admin.pk).delete()
            institution.delete()
            raise

        # Credentials first and in plain ASCII, so they survive any console encoding.
        rows = [
            ("Institution ID", str(institution.pk)),
            ("Slug", institution.slug),
            ("Admin", f"{admin.name} <{admin.email}>"),
        ]
        if generated:
            rows.append(("Temporary password", password))
        rows.append(("Sign in at", f"{settings.FRONTEND_URL.rstrip('/')}/login?school={institution.slug}"))
        width = max(len(label) for label, _ in rows)
        out.write("")
        for label, value in rows:
            out.write(f"  {label.ljust(width)}  {value}")
        out.write(self.style.SUCCESS(f"\nOnboarded {institution.name}."))

        note = "Share these details with the admin over a secure channel."
        if generated:
            note = "The temporary password is shown only once. " + note
        out.write(f"\n{note}\nThey'll be asked to choose their own password at first sign-in.\n")
