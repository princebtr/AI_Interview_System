"""Institution logo and theme colours set by platform staff in the Django admin
(/admin), and how they reach every portal and the sign-in page."""
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from accounts.tests import ApiTestCase, make_institution, make_user
from institutions import theme
from institutions.models import Institution

CHANGE = "/admin/institutions/institution/{}/change/"


class PaletteTests(SimpleTestCase):
    def test_default_theme(self):
        self.assertIsNone(theme.palette("", ""))

    def test_every_variable_the_css_uses(self):
        variables = theme.palette("#2563eb", "#7c3aed")
        steps = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900)
        expected = {f"--color-{name}-{step}" for name in ("accent", "accent2") for step in steps}
        solids = {f"--color-{p}{name}" for p in ("", "on-") for name in ("primary", "secondary")}
        self.assertEqual(set(variables), expected | solids)
        self.assertEqual(variables["--color-accent-600"], "#2563eb")  # already readable: kept as chosen
        self.assertEqual(variables["--color-secondary"], "#7c3aed")
        self.assertEqual(variables["--color-on-primary"], "#ffffff")

    def test_chosen_colours_are_used_exactly_as_solid_fills(self):
        variables = theme.palette("#7C3AED", "#F97316")
        self.assertEqual((variables["--color-primary"], variables["--color-secondary"]), ("#7c3aed", "#f97316"))
        self.assertFalse(any("gradient" in value for value in variables.values()))

    def test_light_colours_keep_their_fill_and_get_dark_text(self):
        variables = theme.palette("#facc15", "#ffffff")
        self.assertEqual(variables["--color-primary"], "#facc15")  # not darkened
        self.assertEqual(variables["--color-on-primary"], theme.INK)
        self.assertGreaterEqual(theme.contrast(variables["--color-primary"], variables["--color-on-primary"]), 4.5)
        for name in ("--color-accent-600", "--color-accent2-600"):  # still readable as text on white
            self.assertGreaterEqual(theme.contrast_with_white(variables[name]), 4.5, name)
        self.assertEqual(variables["--color-accent-50"][:3], "#ff")  # soft tints stay light

    def test_scale_runs_light_to_dark(self):
        values = [theme.luminance(c) for _, c in sorted(theme.scale("#0d9488").items())]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_secondary_defaults_to_primary(self):
        variables = theme.palette("#2563eb", "")
        self.assertEqual(variables["--color-accent2-600"], variables["--color-accent-600"])
        self.assertEqual(variables["--color-secondary"], "#2563eb")


class DjangoAdminTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution(name="Greenfield School")
        self.staff = get_user_model().objects.create_superuser("platform", "platform@example.com", "Platform-2026x")
        self.client.force_login(self.staff)

    def form(self, **changes):
        data = {
            "name": self.institution.name,
            "slug": self.institution.slug,
            "type": self.institution.type,
            "website": "",
            "address": "",
            "academic_year": "2026-27",
            "is_active": "on",
            "primary_color": "#4f46e5",
            "secondary_color": "#7c3aed",
        }
        data.update(changes)
        return {k: v for k, v in data.items() if v is not None}

    def save(self, **changes):
        return self.client.post(CHANGE.format(self.institution.pk), self.form(**changes))

    def png(self):
        buffer = io.BytesIO()
        Image.new("RGB", (600, 300), (5, 150, 105)).save(buffer, "PNG")
        return SimpleUploadedFile("crest.png", buffer.getvalue(), content_type="image/png")

    def test_admin_lists_institutions(self):
        response = self.client.get("/admin/institutions/institution/")
        self.assertStatus(response, 200)
        self.assertContains(response, "Greenfield School")
        self.assertStatus(self.client.get(CHANGE.format(self.institution.pk)), 200)

    def test_staff_only(self):
        self.client.logout()
        response = self.client.get(CHANGE.format(self.institution.pk))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_set_colours_and_logo(self):
        response = self.save(primary_color="#0D9488", secondary_color="#2563EB", logo_file=self.png())
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors)
        self.institution.refresh_from_db()
        self.assertEqual((self.institution.primary_color, self.institution.secondary_color), ("#0d9488", "#2563eb"))
        self.assertTrue(self.institution.logo_version)
        with Image.open(io.BytesIO(bytes(self.institution.logo))) as stored:
            self.assertEqual((stored.format, max(stored.size)), ("PNG", 256))

        # Every role of the institution gets the same theme with its user data...
        for role in ("admin", "educator", "student"):
            user = make_user(self.institution, role)
            me = self.api_get("/api/auth/me", user=user).json()["user"]["institution"]
            self.assertEqual(me["theme"]["primary"], "#0d9488")
            self.assertEqual(me["theme"]["palette"]["--color-secondary"], "#2563eb")
            self.assertEqual(me["logoUrl"], self.institution.logo_url)
        # ...and the public sign-in page shows it too.
        brand = self.client.get(f"/api/institutions/by-slug/{self.institution.slug}").json()
        self.assertEqual(brand["theme"]["secondary"], "#2563eb")
        self.assertStatus(self.client.get(brand["logoUrl"]), 200)

    def test_back_to_default_colours_and_remove_logo(self):
        self.save(primary_color="#0d9488", logo_file=self.png())
        self.save(use_default_theme="on", remove_logo="on")
        self.institution.refresh_from_db()
        self.assertEqual((self.institution.primary_color, self.institution.logo_version), ("", ""))
        me = self.api_get("/api/auth/me", user=make_user(self.institution, "student")).json()["user"]["institution"]
        self.assertEqual(me["theme"], {"primary": None, "secondary": None, "palette": None})
        self.assertIsNone(me["logoUrl"])

    def test_invalid_input_is_refused(self):
        response = self.save(primary_color="blue")
        self.assertEqual(response.status_code, 200)
        self.assertIn("primary_color", response.context["adminform"].form.errors)
        not_image = SimpleUploadedFile("logo.png", b"not an image", content_type="image/png")
        response = self.save(logo_file=not_image)
        self.assertIn("logo_file", response.context["adminform"].form.errors)
        self.institution.refresh_from_db()
        self.assertEqual(self.institution.primary_color, "")

    def test_other_institutions_are_untouched(self):
        other = make_institution(name="Other School")
        self.save(primary_color="#0d9488")
        self.assertEqual(Institution.objects.get(pk=other.pk).primary_color, "")
