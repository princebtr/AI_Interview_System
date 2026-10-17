"""Platform staff work in the Django admin (/admin): onboarding an institution
with its first admin, and supporting accounts (add, reset password)."""
import re

from django.contrib.auth import get_user_model

from accounts.models import User
from accounts.tests import ApiTestCase, make_institution, make_user
from institutions.models import AuditLog, Cohort, Institution

ADD = "/admin/institutions/institution/add/"


class OnboardingTests(ApiTestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_superuser("platform", "platform@example.com", "Platform-2026x")
        self.client.force_login(self.staff)

    def onboard(self, **changes):
        data = {
            "name": "Hillview Public School",
            "slug": "hillview",
            "type": "school",
            "website": "",
            "address": "",
            "academic_year": "2026-27",
            "is_active": "on",
            "admin_name": "Asha Rao",
            "admin_email": "Asha@Hillview.edu",
            "admin_password": "",
            "use_default_theme": "on",
            "primary_color": "#4f46e5",
            "secondary_color": "#7c3aed",
        }
        data.update(changes)
        return self.client.post(ADD, data, follow=True)

    def test_add_form_asks_for_the_first_admin(self):
        response = self.client.get(ADD)
        self.assertStatus(response, 200)
        self.assertContains(response, "First admin")
        self.assertContains(response, 'name="admin_email"')

    def test_onboarding_creates_institution_and_admin(self):
        response = self.onboard()
        institution = Institution.objects.get(slug="hillview")
        admin = User.objects.get(email="asha@hillview.edu")
        self.assertEqual((admin.institution_id, admin.role, admin.must_change_password), (institution.pk, "admin", True))
        self.assertTrue(AuditLog.objects.filter(institution=institution, action="institution.onboarded").exists())

        # The generated password is shown once, and it works.
        page = response.content.decode()
        password = re.search(r"temporary password <code>([^<]+)</code>", page).group(1)
        self.assertTrue(admin.check_password(password))
        self.assertIn("/login?school=hillview", page)

    def test_existing_email_is_refused_and_nothing_is_created(self):
        make_user(make_institution(name="Other"), "admin", email="asha@hillview.edu")
        response = self.onboard()
        self.assertContains(response, "already exists")
        self.assertFalse(Institution.objects.filter(slug="hillview").exists())

    def test_change_page_lists_people_and_cohorts(self):
        institution = make_institution(name="Greenfield")
        make_user(institution, "admin")
        Cohort.objects.create(institution=institution, name="CSE-2027")
        response = self.client.get(f"/admin/institutions/institution/{institution.pk}/change/")
        self.assertContains(response, "1 admins")
        self.assertContains(response, "CSE-2027")


class UserAdminTests(ApiTestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_superuser("platform", "platform@example.com", "Platform-2026x")
        self.client.force_login(self.staff)
        self.institution = make_institution(name="Greenfield")
        self.cohort = Cohort.objects.create(institution=self.institution, name="CSE-2027")

    def test_add_student_needs_a_cohort_of_the_same_institution(self):
        other = Cohort.objects.create(institution=make_institution(name="Other"), name="X")
        data = {"name": "Ravi Kumar", "email": "ravi@greenfield.edu", "role": "student", "institution": self.institution.pk, "cohort": other.pk}
        response = self.client.post("/admin/accounts/user/add/", data)
        self.assertContains(response, "another institution")
        data["cohort"] = self.cohort.pk
        response = self.client.post("/admin/accounts/user/add/", data, follow=True)
        user = User.objects.get(email="ravi@greenfield.edu")
        password = re.search(r"<code>([^<]+)</code>", response.content.decode()).group(1)
        self.assertTrue(user.check_password(password))
        self.assertTrue(user.must_change_password)

    def test_reset_password_action(self):
        user = make_user(self.institution, "educator")
        version = user.token_version
        response = self.client.post(
            "/admin/accounts/user/",
            {"action": "reset_password", "_selected_action": [user.pk]},
            follow=True,
        )
        user.refresh_from_db()
        password = re.search(r"<code>([^<]+)</code>", response.content.decode()).group(1)
        self.assertTrue(user.check_password(password))
        self.assertEqual((user.must_change_password, user.token_version), (True, version + 1))
