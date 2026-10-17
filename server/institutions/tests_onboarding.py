"""Tests for `manage.py onboard_institution`, the only way a tenant is created.

There is no public sign-up: the platform operator onboards an institution and
its first admin, who then adds everyone else through the API.
"""
import io
import re
import uuid
from datetime import date
from unittest import mock

from django.core.management import CommandError, call_command
from django.db import DatabaseError
from django.test import SimpleTestCase
from django.utils import timezone

from accounts import validators
from accounts.models import User
from accounts.tests import (
    COHORTS,
    ME,
    UPDATE_PASSWORD,
    USERS,
    ApiTestCase,
    make_institution,
    make_user,
    unique_email,
)
from accounts.passwords import generate_password as generate_temp_password
from institutions.management.commands.onboard_institution import default_academic_year
from institutions.models import AuditLog, Institution

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
BCRYPT_PATTERN = r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$"


def policy_errors(password):
    errors = []
    validators.clean_new_password(password, errors)
    return errors


def expected_academic_year(today):
    """Academic years start in June."""
    start = today.year if today.month >= 6 else today.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


class OnboardingHelperTests(SimpleTestCase):
    def test_default_academic_year_starts_in_june(self):
        cases = {
            date(2026, 10, 3): "2026-27",
            date(2027, 3, 1): "2026-27",
            date(2026, 6, 1): "2026-27",
            date(2026, 5, 31): "2025-26",
            date(2099, 12, 31): "2099-00",
            date(2000, 1, 1): "1999-00",
        }
        for today, expected in cases.items():
            with self.subTest(today=today):
                self.assertEqual(default_academic_year(today), expected)

    def test_generated_temporary_passwords_meet_the_policy(self):
        passwords = [generate_temp_password() for _ in range(200)]
        for password in passwords:
            self.assertEqual(len(password), 14)
            self.assertEqual(policy_errors(password), [], password)
        self.assertEqual(len(set(passwords)), len(passwords))


class OnboardCommandTests(ApiTestCase):
    def onboard(self, **options):
        """Run the command with --no-input. A None value leaves that option out."""
        values = {
            "name": "Springfield College",
            "type": "college",
            "admin_name": "Asha Rao",
            "admin_email": unique_email("asha"),
        }
        values.update(options)
        # --flag=value, so values that start with "-" aren't parsed as flags.
        args = ["--no-input"] + [
            f"--{key.replace('_', '-')}" if value is True else f"--{key.replace('_', '-')}={value}"
            for key, value in values.items()
            if value is not None
        ]
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=AssertionError("prompted for input")), \
                mock.patch("getpass.getpass", side_effect=AssertionError("prompted for a password")):
            call_command("onboard_institution", *args, stdout=out, stderr=io.StringIO())
        return out.getvalue()

    def assertRejected(self, message, **options):
        before = (Institution.objects.count(), User.objects.count())
        with self.assertRaisesMessage(CommandError, message):
            self.onboard(**options)
        after = (Institution.objects.count(), User.objects.count())
        self.assertEqual(after, before, "a failed onboarding left records behind")

    # --- success --------------------------------------------------------- #

    def test_creates_the_institution_and_its_first_admin(self):
        admin_email = unique_email("Asha", "Springfield.EDU")
        out = self.onboard(
            name="Springfield College",
            type="college",
            website="springfield.edu",
            address="1 College Road, Springfield",
            admin_name="Asha Rao",
            admin_email=admin_email,
        )

        institution = Institution.objects.get()
        self.assertEqual(institution.name, "Springfield College")
        self.assertEqual(institution.slug, "springfield-college")
        self.assertEqual(institution.type, "college")
        self.assertEqual(institution.website, "https://springfield.edu")
        self.assertEqual(institution.address, "1 College Road, Springfield")
        self.assertRegex(institution.academic_year, r"^\d{4}-\d{2}$")
        self.assertEqual(institution.academic_year, expected_academic_year(timezone.localdate()))
        self.assertTrue(institution.is_active)

        admin = User.objects.get()
        self.assertEqual(admin.institution_id, institution.pk)
        self.assertEqual(admin.role, "admin")
        self.assertEqual(admin.name, "Asha Rao")
        self.assertEqual(admin.email, admin_email.lower())
        self.assertIsNone(admin.cohort_id)
        self.assertTrue(admin.must_change_password)
        self.assertRegex(admin.password, BCRYPT_PATTERN)

        match = re.search(r"Temporary password\s+(\S+)", out)
        self.assertIsNotNone(match, f"no temporary password printed:\n{out}")
        temporary = match.group(1)
        self.assertTrue(admin.check_password(temporary))
        self.assertNotIn(temporary, admin.password)
        self.assertEqual(policy_errors(temporary), [])
        for detail in (str(institution.pk), "springfield-college", admin.email):
            self.assertIn(detail, out)

        # The admin can sign in with it and is told to replace it.
        response = self.api_login(admin.email, temporary)
        self.assertStatus(response, 200)
        user = response.json()["user"]
        self.assertIs(user["mustChangePassword"], True)
        self.assertEqual(user["role"], "admin")
        self.assertEqual(user["institution"]["id"], str(institution.pk))

    def test_given_password_is_used_but_never_printed(self):
        out = self.onboard(admin_password="Welcome2026")
        admin = User.objects.get()
        self.assertTrue(admin.check_password("Welcome2026"))
        self.assertTrue(admin.must_change_password)
        self.assertNotIn("Welcome2026", out)
        self.assertNotIn("Temporary password", out)

    def test_explicit_slug_website_type_and_academic_year_are_kept(self):
        self.onboard(
            slug="spring-col",
            website="http://springfield.edu/admissions",
            academic_year="2026-2027",
            type="university",
        )
        institution = Institution.objects.get()
        self.assertEqual(institution.slug, "spring-col")
        self.assertEqual(institution.website, "http://springfield.edu/admissions")
        self.assertEqual(institution.academic_year, "2026-2027")
        self.assertEqual(institution.type, "university")

    def test_website_and_address_are_optional(self):
        self.onboard()
        institution = Institution.objects.get()
        self.assertEqual((institution.website, institution.address), ("", ""))

    def test_long_names_get_a_valid_default_slug(self):
        # 89 characters (names may have up to 150); slugs are capped at 80.
        name = ("Jawaharlal Nehru Technological University College of Engineering "
                "and Technology Hyderabad")
        self.onboard(name=name)
        slug = Institution.objects.get().slug
        self.assertRegex(slug, SLUG_PATTERN)
        self.assertLessEqual(len(slug), 80)

    # --- rejected input ---------------------------------------------------- #

    def test_duplicate_name_is_rejected_case_insensitively(self):
        make_institution(name="Springfield College", slug="springfield-college")
        self.assertRejected("An institution named", name="SPRINGFIELD college", slug="spring-2")
        self.assertRejected("An institution named", name="  springfield college ", slug="spring-3")

    def test_regex_metacharacters_in_names_do_not_false_match(self):
        make_institution(name="StX Mary's", slug="stx-marys")
        self.onboard(name="St. Mary's")  # must not be mistaken for "StX Mary's"
        self.assertTrue(Institution.objects.filter(name="St. Mary's", slug="st-marys").exists())
        self.assertRejected("An institution named", name="st. mary's", slug="st-marys-2")

        for name in ("Springfield (North) College", "A+ Academy", "Why? School",
                     "Star* Institute", "[Bracket] College", "Back\\slash School",
                     "Dollar$ School", "^Caret School", "Pipe|School"):
            with self.subTest(name=name):
                self.onboard(name=name)
                self.assertTrue(Institution.objects.filter(name=name).exists())
                self.assertRejected("An institution named", name=name.upper(),
                                    slug=f"dup-{uuid.uuid4().hex[:8]}")
        self.assertEqual(Institution.objects.count(), 11)

    def test_taken_slug_is_rejected(self):
        make_institution(name="Alpha School", slug="alpha")
        self.assertRejected('The slug "alpha" is taken', name="Beta School", slug="alpha")

    def test_slug_derived_from_the_name_must_be_free(self):
        make_institution(name="Springfield College (Old Campus)", slug="springfield-college")
        self.assertRejected('The slug "springfield-college" is taken', name="Springfield College")

    def test_malformed_slugs_are_rejected(self):
        for slug in ("Bad Slug", "UPPER", "double--hyphen", "-leading", "trailing-",
                     "under_score", "x" * 81):
            with self.subTest(slug=slug):
                self.assertRejected("Slug may only contain", slug=slug)

    def test_duplicate_admin_email_is_rejected(self):
        existing = make_user(make_institution(), "educator")
        self.assertRejected("An account with", admin_email=existing.email.upper())

    def test_invalid_website_is_rejected(self):
        for website in ("not a url", "ftp://files.springfield.edu", "https://", "http://",
                        "javascript:alert(1)"):
            with self.subTest(website=website):
                self.assertRejected("Enter a valid website URL.", website=website)

    def test_weak_admin_password_is_rejected(self):
        for weak in ("short", "alllowercase1", "NoDigitsHere", "Aa1" + "x" * 70):
            with self.subTest(password=weak):
                self.assertRejected("--admin-password", admin_password=weak)

    def test_missing_required_values_fail_without_prompting(self):
        cases = [
            ({"name": None}, "Name is required."),
            ({"name": "   "}, "Name is required."),
            ({"type": None}, "is required."),
            ({"admin_name": None}, "Full name is required."),
            ({"admin_email": None}, "Email is required."),
        ]
        for options, message in cases:
            with self.subTest(options=options):
                self.assertRejected(message, **options)

    def test_invalid_values_are_rejected(self):
        cases = [
            ({"type": "spaceship"}, "invalid choice"),
            ({"academic_year": "2026/27"}, "Use the format 2026-27."),
            ({"academic_year": "26-27"}, "Use the format 2026-27."),
            ({"academic_year": "2026-7"}, "Use the format 2026-27."),
            ({"academic_year": "this year"}, "Use the format 2026-27."),
            ({"admin_name": "A"}, "Name must be 2-50 characters"),
            ({"admin_email": "not-an-email"}, "Please provide a valid email"),
            ({"name": "x" * 151}, "2-150 characters"),
        ]
        for options, message in cases:
            with self.subTest(options=options):
                self.assertRejected(message, **options)

    # --- partial failure ------------------------------------------------------ #

    def test_institution_is_removed_if_the_admin_cannot_be_saved(self):
        with mock.patch.object(User, "save", side_effect=DatabaseError("simulated write failure")):
            with self.assertRaises(DatabaseError):
                self.onboard(name="Rollback College")
        self.assertFalse(Institution.objects.exists())
        self.assertFalse(User.objects.exists())

        # Nothing was left behind, so the same onboarding works afterwards.
        self.onboard(name="Rollback College")
        self.assertEqual(Institution.objects.get().slug, "rollback-college")
        self.assertEqual(User.objects.get().role, "admin")


    def test_ctrl_c_mid_way_leaves_nothing_behind(self):
        with mock.patch.object(User, "save", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.onboard(name="Interrupted College")
        self.assertFalse(Institution.objects.exists())
        self.assertFalse(User.objects.exists())

    def test_awkward_names_get_a_slug_the_validator_accepts(self):
        self.onboard(name="St_Xavier's  College")
        self.assertRegex(Institution.objects.get().slug, SLUG_PATTERN)

    def test_names_without_latin_characters_ask_for_a_slug(self):
        self.assertRejected("--slug", name="東京大学")
        self.onboard(name="東京大学", slug="tokyo-university")
        self.assertEqual(Institution.objects.get().slug, "tokyo-university")

    def test_onboarding_is_recorded_in_the_activity_log(self):
        self.onboard(name="Logged College")
        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "institution.onboarded")
        self.assertIsNone(entry.actor_id)

    def test_pre_tenancy_accounts_need_an_explicit_attach(self):
        orphan = make_user(None, "student", email=unique_email("orphan"))
        self.assertRejected("--attach-existing", admin_email=orphan.email)

        old_version = orphan.token_version
        out = self.onboard(name="Adopting College", admin_email=orphan.email, attach_existing=True)
        orphan.refresh_from_db()
        self.assertEqual(orphan.institution.name, "Adopting College")
        self.assertEqual(orphan.role, "admin")
        self.assertTrue(orphan.must_change_password)
        self.assertGreater(orphan.token_version, old_version)
        password = re.search(r"Temporary password\s+(\S+)", out).group(1)
        self.assertTrue(orphan.check_password(password))


class OnboardInteractiveTests(ApiTestCase):
    def run_interactive(self, answers, passwords):
        answers = iter(answers)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("builtins.input", side_effect=lambda prompt="": next(answers)), \
                mock.patch("getpass.getpass", side_effect=list(passwords)):
            call_command("onboard_institution", stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_reprompts_until_every_value_is_valid(self):
        email = unique_email("asha")
        out, err = self.run_interactive(
            answers=[
                "",                     # Name: required, asked again
                "Springfield College",
                "spaceship",            # Type: invalid, asked again
                "College",              # cleaned to "college"
                "",                     # Slug: accept the default
                "springfield.edu",      # Website
                "",                     # Address: optional
                "",                     # Academic year: accept the default
                "Asha Rao",
                "not-an-email",         # Email: invalid, asked again
                email.upper(),
                "y",                    # Create this institution?
            ],
            passwords=["weak", "Welcome2026", "Welcome2026"],
        )
        for message in ("Name is required.", "Type must be one of", "Please provide a valid email",
                        "Password must"):
            self.assertIn(message, err)

        institution = Institution.objects.get()
        self.assertEqual(
            (institution.name, institution.type, institution.slug, institution.website),
            ("Springfield College", "college", "springfield-college", "https://springfield.edu"),
        )
        self.assertEqual(institution.academic_year, expected_academic_year(timezone.localdate()))
        admin = User.objects.get()
        self.assertEqual(admin.email, email)
        self.assertTrue(admin.check_password("Welcome2026"))
        self.assertTrue(admin.must_change_password)
        self.assertNotIn("Welcome2026", out)

    def test_declining_the_confirmation_creates_nothing(self):
        for confirmation in ("n", ""):
            with self.subTest(confirmation=confirmation):
                with self.assertRaisesMessage(CommandError, "Cancelled"):
                    self.run_interactive(
                        answers=["Springfield College", "college", "", "", "", "", "Asha Rao",
                                 unique_email("asha"), confirmation],
                        passwords=[""],  # blank: generate one
                    )
        self.assertFalse(Institution.objects.exists())
        self.assertFalse(User.objects.exists())


class OnboardingJourneyTests(ApiTestCase):
    """From the operator's command to a signed-in student, through the API."""

    def test_admin_adds_staff_and_a_student_who_then_signs_in(self):
        admin_email = unique_email("principal")
        call_command(
            "onboard_institution", "--no-input", "--name", "Riverdale School", "--type", "school",
            "--admin-name", "Pat Principal", "--admin-email", admin_email,
            "--admin-password", "Welcome2026", stdout=io.StringIO(),
        )
        institution = Institution.objects.get(slug="riverdale-school")

        # The admin signs in with the temporary password and must replace it.
        login = self.api_login(admin_email, "Welcome2026")
        self.assertStatus(login, 200)
        token = login.json()["token"]
        self.assertPasswordChangeRequired(self.api_get(USERS, token=token))
        changed = self.api_put(
            UPDATE_PASSWORD, {"currentPassword": "Welcome2026", "newPassword": "Principal2026"},
            token=token,
        )
        self.assertStatus(changed, 200)
        token = changed.json()["token"]

        # They add a cohort, an educator, another admin and a student in the cohort.
        cohort = self.api_post(COHORTS, {"name": "Grade 10 A"}, token=token)
        self.assertStatus(cohort, 201)
        cohort_id = cohort.json()["cohort"]["id"]
        student_email = unique_email("student")
        new_users = [
            {"name": "Tara Teacher", "email": unique_email("teacher"), "role": "educator",
             "password": "Teacher2026"},
            {"name": "Vice Principal", "email": unique_email("vice"), "role": "admin",
             "password": "Deputy2026"},
            {"name": "Sam Student", "email": student_email, "role": "student",
             "password": "Student2026", "cohortId": cohort_id},
        ]
        for body in new_users:
            with self.subTest(role=body["role"]):
                self.assertStatus(self.api_post(USERS, body, token=token), 201)

        listing = self.api_get(USERS, token=token).json()
        self.assertEqual(listing["counts"], {"admin": 2, "educator": 1, "student": 1})
        cohorts = self.api_get(COHORTS, token=token).json()["cohorts"]
        self.assertEqual(
            [{k: c[k] for k in ("id", "name", "studentCount")} for c in cohorts],
            [{"id": cohort_id, "name": "Grade 10 A", "studentCount": 1}],
        )

        # The student lands in the right tenant and cohort, and must set a password.
        student_login = self.api_login(student_email, "Student2026")
        self.assertStatus(student_login, 200)
        student = student_login.json()["user"]
        self.assertEqual(student["institution"]["id"], str(institution.pk))
        self.assertEqual(student["cohort"], {"id": cohort_id, "name": "Grade 10 A"})
        self.assertIs(student["mustChangePassword"], True)
        student_token = student_login.json()["token"]
        self.assertPasswordChangeRequired(self.api_get(COHORTS, token=student_token))

        changed = self.api_put(
            UPDATE_PASSWORD, {"currentPassword": "Student2026", "newPassword": "MyOwnPass1"},
            token=student_token,
        )
        self.assertStatus(changed, 200)
        student_token = changed.json()["token"]
        self.assertStatus(self.api_get(ME, token=student_token), 200)
        # Still a student: no administration.
        self.assertStatus(self.api_get(USERS, token=student_token), 403)
        self.assertStatus(self.api_get(COHORTS, token=student_token), 403)
