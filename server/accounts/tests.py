"""Tests for sign-in, token authentication, temporary passwords and profile updates.

The backend is django-mongodb-backend, which has no transactions: Django's
TestCase therefore flushes the database after every test instead of rolling
back, so every fixture is built in setUp().

The helpers defined at the top of this module (factories and ApiTestCase) are
also used by the institutions app's tests.
"""
import base64
import json
import time
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest import mock

import bcrypt
import jwt
from bson import ObjectId
from django.conf import settings
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.auth import create_token
from accounts.models import LoginAttempt, User
from accounts.throttle import throttle_key
from ai.models import InterviewSession
from institutions.models import Cohort, Institution

# Captured at import time, before any override, so a test can compare against
# the cost factor that production really uses.
PRODUCTION_BCRYPT_ROUNDS = settings.BCRYPT_ROUNDS
# bcrypt's minimum cost; keeps fixtures fast. Behaviour doesn't depend on it.
FAST_BCRYPT_ROUNDS = 4

PASSWORD = "Secret123"

ME = "/api/auth/me"
LOGIN = "/api/auth/login"
LOGOUT = "/api/auth/logout"
UPDATE_DETAILS = "/api/auth/updatedetails"
UPDATE_PASSWORD = "/api/auth/updatepassword"
USERS = "/api/institution/users"
COHORTS = "/api/institution/cohorts"
AI_SESSION = "/api/ai/session"


# --------------------------------------------------------------------------- #
# Factories and helpers (shared with institutions/tests*.py)                  #
# --------------------------------------------------------------------------- #


def unique_email(prefix="user", domain="example.edu"):
    return f"{prefix}.{uuid.uuid4().hex[:12]}@{domain}"


def make_institution(name=None, **fields):
    suffix = uuid.uuid4().hex[:10]
    fields.setdefault("slug", f"inst-{suffix}")
    fields.setdefault("type", "college")
    fields.setdefault("academic_year", "2026-27")
    return Institution.objects.create(name=name or f"Institution {suffix}", **fields)


def make_cohort(institution, name=None):
    return Cohort.objects.create(
        institution=institution, name=name or f"Cohort {uuid.uuid4().hex[:8]}"
    )


def make_user(institution, role="student", *, password=PASSWORD, email=None, name=None,
              cohort=None, **fields):
    user = User(
        institution=institution,
        role=role,
        cohort=cohort,
        email=email or unique_email(role),
        name=name or f"Test {role.title()}",
        **fields,
    )
    user.set_password(password)
    user.save()
    return user


def bcrypt_cost(hashed):
    """The cost factor of a bcrypt hash such as $2b$12$..."""
    if isinstance(hashed, bytes):
        hashed = hashed.decode()
    return int(hashed.split("$")[2])


def remove_institution_document(institution):
    """Delete an institution's document straight from MongoDB.

    The ORM refuses (users PROTECT it), but MongoDB has no foreign keys: an
    operator deleting a tenant in Atlas/Compass leaves its users pointing at a
    missing institution.
    """
    result = connection.get_collection(Institution._meta.db_table).delete_one(
        {"_id": institution.pk}
    )
    assert result.deleted_count == 1, "institution document was not removed"


def signed_token(claims, secret=None):
    return jwt.encode(claims, secret or settings.JWT_SECRET, algorithm="HS256")


@override_settings(BCRYPT_ROUNDS=FAST_BCRYPT_ROUNDS)
class ApiTestCase(TestCase):
    """JSON request helpers. Authenticate with `user=` (a Bearer token is
    minted for them) or `token=`; send a raw body with `raw=`."""

    def request(self, method, path, body=None, *, user=None, token=None, params=None, raw=None):
        headers = {}
        if user is not None:
            token = create_token(user)
        if token is not None:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        send = getattr(self.client, method.lower())
        if method.upper() == "GET":
            return send(path, params or {}, **headers)
        payload = raw if raw is not None else (body if body is not None else {})
        return send(path, payload, content_type="application/json", **headers)

    def api_get(self, path, params=None, **kwargs):
        return self.request("GET", path, params=params, **kwargs)

    def api_post(self, path, body=None, **kwargs):
        return self.request("POST", path, body, **kwargs)

    def api_put(self, path, body=None, **kwargs):
        return self.request("PUT", path, body, **kwargs)

    def api_login(self, email, password):
        return self.api_post(LOGIN, {"email": email, "password": password})

    def assertStatus(self, response, status):
        self.assertEqual(
            response.status_code,
            status,
            f"expected HTTP {status}, got {response.status_code}: "
            f"{response.content.decode(errors='replace')[:800]}",
        )

    def assertFieldErrors(self, response, *fields):
        """A 400 whose `errors` name exactly these fields."""
        self.assertStatus(response, 400)
        body = response.json()
        self.assertIs(body["success"], False)
        self.assertEqual({e["field"] for e in body.get("errors", [])}, set(fields), body)
        return body

    def assertPasswordChangeRequired(self, response):
        self.assertStatus(response, 403)
        self.assertEqual(response.json().get("code"), "password_change_required")


# --------------------------------------------------------------------------- #
# Sign-up                                                                      #
# --------------------------------------------------------------------------- #


class SignupRemovedTests(ApiTestCase):
    def test_register_endpoint_no_longer_exists(self):
        body = {"name": "Eve Intruder", "email": unique_email("eve"), "password": PASSWORD,
                "role": "admin"}
        for path in ("/api/auth/register", "/api/auth/register/"):
            with self.subTest(path=path):
                self.assertEqual(self.api_post(path, body).status_code, 404)
                self.assertEqual(self.api_get(path).status_code, 404)
        self.assertFalse(User.objects.exists())


# --------------------------------------------------------------------------- #
# Login                                                                        #
# --------------------------------------------------------------------------- #


class LoginTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution(
            name="Springfield College", website="https://springfield.edu"
        )
        self.cohort = make_cohort(self.institution, "CSE 2027")
        self.user = make_user(
            self.institution, "student", cohort=self.cohort, name="Asha Rao",
            email=unique_email("asha"),
        )

    def test_success_returns_token_and_user(self):
        response = self.api_login(self.user.email, PASSWORD)
        self.assertStatus(response, 200)
        body = response.json()
        self.assertIs(body["success"], True)

        claims = jwt.decode(body["token"], settings.JWT_SECRET, algorithms=["HS256"])
        self.assertEqual(claims["id"], str(self.user.pk))
        self.assertEqual(claims["exp"] - claims["iat"], settings.JWT_EXPIRE_DAYS * 86400)

        user = body["user"]
        self.assertEqual(user["id"], str(self.user.pk))
        self.assertEqual(user["name"], "Asha Rao")
        self.assertEqual(user["email"], self.user.email)
        self.assertEqual(user["role"], "student")
        self.assertIs(user["mustChangePassword"], False)
        self.assertEqual(
            user["institution"],
            {
                "id": str(self.institution.pk),
                "name": "Springfield College",
                "slug": self.institution.slug,
                "type": "college",
                "academicYear": "2026-27",
                "website": "https://springfield.edu",
                "logoUrl": None,
                "theme": {"primary": None, "secondary": None, "palette": None},  # default colours
            },
        )
        self.assertEqual(user["cohort"], {"id": str(self.cohort.pk), "name": "CSE 2027"})
        self.assertIsNotNone(user["lastLogin"])
        self.assertNotIn("password", user)
        self.assertNotIn(self.user.password, response.content.decode())

        self.assertEqual(claims["ver"], self.user.token_version)
        self.assertNotIn("token", response.cookies)  # Bearer tokens only

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)
        self.assertFalse(LoginAttempt.objects.exists(), "a successful login clears the attempts")

    def test_email_is_trimmed_and_case_insensitive(self):
        response = self.api_login(f"  {self.user.email.upper()}  ", PASSWORD)
        self.assertStatus(response, 200)
        self.assertEqual(response.json()["user"]["id"], str(self.user.pk))

    def test_wrong_password_is_401_invalid_credentials(self):
        response = self.api_login(self.user.email, "Wrong1234")
        self.assertStatus(response, 401)
        body = response.json()
        self.assertEqual(body["message"], "Invalid credentials")
        self.assertNotIn("token", body)
        self.assertNotIn("token", response.cookies)
        self.assertEqual(LoginAttempt.objects.count(), 1)

    def test_unknown_email_is_401_invalid_credentials(self):
        response = self.api_login(unique_email("nobody"), PASSWORD)
        self.assertStatus(response, 401)
        self.assertEqual(response.json()["message"], "Invalid credentials")
        self.assertNotIn("token", response.cookies)

    def test_missing_or_non_string_credentials_are_400(self):
        bodies = [
            {},
            {"email": self.user.email},
            {"password": PASSWORD},
            {"email": "", "password": ""},
            {"email": [self.user.email], "password": PASSWORD},
            {"email": self.user.email, "password": 12345678},
        ]
        for body in bodies:
            with self.subTest(body=body):
                self.assertStatus(self.api_post(LOGIN, body), 400)

    def test_malformed_json_is_400(self):
        for raw in ("{not json", "[1, 2]", '"just a string"', "null"):
            with self.subTest(raw=raw):
                self.assertStatus(self.api_post(LOGIN, raw=raw), 400)

    def test_sixth_attempt_in_the_window_is_throttled(self):
        for attempt in range(1, 6):
            with self.subTest(attempt=attempt):
                self.assertStatus(self.api_login(self.user.email, "Wrong1234"), 401)

        # Throttled now: even the right password isn't checked and no token is issued.
        response = self.api_login(self.user.email, PASSWORD)
        self.assertStatus(response, 429)
        self.assertNotIn("token", response.json())
        retry_after = int(response["Retry-After"])
        self.assertGreater(retry_after, 0)
        self.assertLessEqual(retry_after, settings.LOGIN_WINDOW_MINUTES * 60)

    def test_registered_and_unknown_emails_are_throttled_identically(self):
        ghost = unique_email("ghost")
        known = [self.api_login(self.user.email, "Wrong1234") for _ in range(7)]
        unknown = [self.api_login(ghost, "Wrong1234") for _ in range(7)]
        self.assertEqual([r.status_code for r in known], [401] * 5 + [429] * 2)
        self.assertEqual([r.status_code for r in unknown], [r.status_code for r in known])
        self.assertEqual(
            [r.json()["message"] for r in unknown[:5]], [r.json()["message"] for r in known[:5]]
        )

    def test_successful_login_clears_the_failures(self):
        for _ in range(4):
            self.assertStatus(self.api_login(self.user.email, "Wrong1234"), 401)
        self.assertStatus(self.api_login(self.user.email, PASSWORD), 200)
        for _ in range(4):
            self.assertStatus(self.api_login(self.user.email, "Wrong1234"), 401)
        self.assertStatus(self.api_login(self.user.email, PASSWORD), 200)

    def test_attempts_older_than_the_window_no_longer_count(self):
        for _ in range(5):
            self.assertStatus(self.api_login(self.user.email, "Wrong1234"), 401)
        self.assertStatus(self.api_login(self.user.email, PASSWORD), 429)
        LoginAttempt.objects.update(
            created_at=timezone.now() - timedelta(minutes=settings.LOGIN_WINDOW_MINUTES + 1)
        )
        self.assertStatus(self.api_login(self.user.email, PASSWORD), 200)

    def test_in_flight_attempts_count_towards_the_limit(self):
        # Attempts are recorded before the password is checked, so parallel
        # guesses can't each see a count below the limit.
        key = throttle_key("login", self.user.email)
        for _ in range(settings.MAX_LOGIN_ATTEMPTS):
            LoginAttempt.objects.create(key=key)
        self.assertStatus(self.api_login(self.user.email, PASSWORD), 429)

    def test_user_without_institution_is_refused_only_after_correct_password(self):
        orphan = make_user(None, "educator")
        self.assertStatus(self.api_login(orphan.email, "Wrong1234"), 401)

        response = self.api_login(orphan.email, PASSWORD)
        self.assertStatus(response, 403)
        self.assertIn("institution", response.json()["message"])
        self.assertNotIn("token", response.json())
        self.assertNotIn("token", response.cookies)

    def test_user_of_deactivated_institution_is_refused_only_after_correct_password(self):
        Institution.objects.filter(pk=self.institution.pk).update(is_active=False)
        self.assertStatus(self.api_login(self.user.email, "Wrong1234"), 401)

        response = self.api_login(self.user.email, PASSWORD)
        self.assertStatus(response, 403)
        self.assertIn("institution", response.json()["message"])
        self.assertNotIn("token", response.json())
        self.assertNotIn("token", response.cookies)

    def test_user_whose_institution_was_removed_is_refused(self):
        remove_institution_document(self.institution)
        self.assertStatus(self.api_login(self.user.email, "Wrong1234"), 401)
        response = self.api_login(self.user.email, PASSWORD)
        self.assertStatus(response, 403)
        self.assertNotIn("token", response.cookies)

    def test_bcrypt_72_byte_limit_is_not_a_back_door(self):
        """bcrypt only looks at 72 bytes; longer guesses must not match on a prefix."""
        exact = "Aa1" + "x" * 69  # 72 bytes: the longest password the policy allows
        user = make_user(self.institution, "educator", password=exact)
        self.assertStatus(self.api_login(user.email, exact + "EXTRA"), 401)
        self.assertStatus(self.api_login(unique_email("ghost"), exact + "EXTRA"), 401)
        self.assertStatus(self.api_login(user.email, exact), 200)

    def test_login_reports_a_pending_password_change(self):
        User.objects.filter(pk=self.user.pk).update(must_change_password=True)
        response = self.api_login(self.user.email, PASSWORD)
        self.assertStatus(response, 200)
        self.assertIs(response.json()["user"]["mustChangePassword"], True)
        self.assertTrue(response.json()["token"])


class LoginTimingTests(ApiTestCase):
    """accounts.models: "unknown-email logins cost the same as real ones", so
    response time can't reveal which emails have accounts."""

    def test_unknown_email_does_the_same_bcrypt_work_as_a_real_account(self):
        with self.settings(BCRYPT_ROUNDS=PRODUCTION_BCRYPT_ROUNDS):
            user = make_user(make_institution(), "educator")
            with mock.patch("accounts.models.bcrypt.checkpw", wraps=bcrypt.checkpw) as checkpw:
                self.assertStatus(self.api_login(user.email, "Wrong1234"), 401)
                known_hash = checkpw.call_args.args[1]
                self.assertStatus(self.api_login(unique_email("ghost"), "Wrong1234"), 401)
                unknown_hash = checkpw.call_args.args[1]

        self.assertEqual(bcrypt_cost(known_hash), PRODUCTION_BCRYPT_ROUNDS)
        self.assertEqual(
            bcrypt_cost(unknown_hash),
            bcrypt_cost(known_hash),
            "an unknown email is checked against a cheaper bcrypt hash than a real "
            "account, so login response time reveals which emails are registered",
        )


# --------------------------------------------------------------------------- #
# Token authentication                                                         #
# --------------------------------------------------------------------------- #


class TokenAuthenticationTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.user = make_user(self.institution, "educator")

    def claims(self, **overrides):
        now = datetime.now(dt_timezone.utc)
        claims = {"id": str(self.user.pk), "iat": now, "exp": now + timedelta(hours=1)}
        claims.update(overrides)
        return claims

    def test_me_requires_a_token(self):
        response = self.api_get(ME)
        self.assertStatus(response, 401)
        self.assertEqual(response.json()["message"], "Not authorized to access this route")

    def test_me_returns_the_signed_in_user(self):
        response = self.api_get(ME, user=self.user)
        self.assertStatus(response, 200)
        user = response.json()["user"]
        self.assertEqual(user["id"], str(self.user.pk))
        self.assertEqual(user["institution"]["id"], str(self.institution.pk))
        self.assertNotIn("password", user)

    def test_bad_tokens_are_rejected(self):
        def b64(data):
            return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

        unsigned = "{}.{}.".format(
            b64({"alg": "none", "typ": "JWT"}),
            b64({"id": str(self.user.pk), "exp": int(time.time()) + 3600}),
        )
        now = datetime.now(dt_timezone.utc)
        cases = {
            "garbage": "not-a-jwt",
            "empty": "",
            "literal none": "none",
            "wrong secret": signed_token(self.claims(), secret="not-the-server-secret"),
            "expired": signed_token(self.claims(exp=now - timedelta(seconds=5))),
            "no subject": signed_token({"iat": now, "exp": now + timedelta(hours=1)}),
            "unknown user": signed_token(self.claims(id=str(ObjectId()))),
            "alg none": unsigned,
        }
        for label, token in cases.items():
            with self.subTest(label):
                self.assertStatus(self.api_get(ME, token=token), 401)

        with self.subTest("non-Bearer scheme"):
            response = self.client.get(ME, HTTP_AUTHORIZATION=f"Token {create_token(self.user)}")
            self.assertStatus(response, 401)

    def test_signed_token_with_malformed_user_id_is_401(self):
        token = signed_token(self.claims(id="not-an-object-id"))
        self.assertStatus(self.api_get(ME, token=token), 401)

    def test_token_of_deleted_user_is_rejected(self):
        token = create_token(self.user)
        self.user.delete()
        self.assertStatus(self.api_get(ME, token=token), 401)

    def test_token_of_user_without_institution_is_rejected(self):
        orphan = make_user(None, "admin")
        self.assertStatus(self.api_get(ME, user=orphan), 401)

    def test_existing_token_stops_working_when_institution_is_deactivated(self):
        token = create_token(self.user)
        self.assertStatus(self.api_get(ME, token=token), 200)

        Institution.objects.filter(pk=self.institution.pk).update(is_active=False)
        self.assertStatus(self.api_get(ME, token=token), 401)
        self.assertStatus(self.api_put(UPDATE_DETAILS, {"name": "Renamed"}, token=token), 401)
        self.assertStatus(self.api_get(COHORTS, token=token), 401)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.name, "Renamed")

        Institution.objects.filter(pk=self.institution.pk).update(is_active=True)
        self.assertStatus(self.api_get(ME, token=token), 200)

    def test_existing_token_stops_working_when_institution_is_removed(self):
        token = create_token(self.user)
        remove_institution_document(self.institution)
        self.assertStatus(self.api_get(ME, token=token), 401)

    def test_no_auth_cookie_is_set_or_accepted(self):
        # Bearer tokens only: cookie auth would need CSRF protection.
        response = self.api_login(self.user.email, PASSWORD)
        self.assertStatus(response, 200)
        self.assertNotIn("token", response.cookies)
        self.client.cookies["token"] = response.json()["token"]
        self.assertStatus(self.api_get(ME), 401)

    def test_json_endpoints_reject_non_json_content_types(self):
        # A cross-site form can post text/plain without a CORS preflight.
        response = self.client.post(
            LOGIN,
            '{"email": "%s", "password": "%s"}' % (self.user.email, PASSWORD),
            content_type="text/plain",
        )
        self.assertStatus(response, 400)

    def test_tokens_from_before_a_password_change_stop_working(self):
        old_token = create_token(self.user)
        self.user.set_password("Another123")
        self.user.token_version += 1
        self.user.save()
        self.assertStatus(self.api_get(ME, token=old_token), 401)
        self.assertStatus(self.api_get(ME, user=self.user), 200)


# --------------------------------------------------------------------------- #
# Temporary passwords                                                          #
# --------------------------------------------------------------------------- #


class LogoutEverywhereTests(ApiTestCase):
    def test_signing_out_everywhere_revokes_every_token(self):
        user = make_user(make_institution(), "educator")
        this_device, other_device = create_token(user), create_token(user)
        self.assertStatus(self.api_get(ME, token=other_device), 200)

        self.assertStatus(self.api_post("/api/auth/logout-all", token=this_device), 200)
        self.assertStatus(self.api_get(ME, token=this_device), 401)
        self.assertStatus(self.api_get(ME, token=other_device), 401)

        # Signing in again works as normal.
        self.assertStatus(self.api_login(user.email, PASSWORD), 200)

    def test_requires_a_token(self):
        self.assertStatus(self.api_post("/api/auth/logout-all"), 401)


class TemporaryPasswordTests(ApiTestCase):
    TEMPORARY = "TempPass1"
    NEW = "BrandNew2"

    def setUp(self):
        self.institution = make_institution()
        self.admin = make_user(
            self.institution, "admin", password=self.TEMPORARY, must_change_password=True,
            name="Pending Admin",
        )

    def change_password(self, current, new, **auth):
        return self.api_put(
            UPDATE_PASSWORD, {"currentPassword": current, "newPassword": new},
            **(auth or {"user": self.admin}),
        )

    def assertStillPending(self):
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.must_change_password)
        self.assertTrue(self.admin.check_password(self.TEMPORARY))

    def test_me_is_allowed(self):
        response = self.api_get(ME, user=self.admin)
        self.assertStatus(response, 200)
        self.assertIs(response.json()["user"]["mustChangePassword"], True)

    def test_other_protected_endpoints_are_blocked(self):
        token = create_token(self.admin)
        new_user = {"name": "New Educator", "email": unique_email("new"), "role": "educator",
                    "password": PASSWORD}
        calls = [
            ("PUT", UPDATE_DETAILS, {"name": "Changed Name"}),
            ("GET", USERS, None),
            ("POST", USERS, new_user),
            ("GET", COHORTS, None),
            ("POST", COHORTS, {"name": "CSE 2027"}),
            ("POST", AI_SESSION, None),
        ]
        for method, path, body in calls:
            with self.subTest(method=method, path=path):
                self.assertPasswordChangeRequired(self.request(method, path, body, token=token))

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.name, "Pending Admin")
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(Cohort.objects.exists())
        self.assertFalse(InterviewSession.objects.exists())

    def test_wrong_current_password_is_400_not_401(self):
        response = self.change_password("Nope12345", self.NEW)
        self.assertStatus(response, 400)
        self.assertEqual(response.json()["message"], "Current password is incorrect")
        self.assertStillPending()

    def test_missing_current_password_is_400(self):
        response = self.api_put(UPDATE_PASSWORD, {"newPassword": self.NEW}, user=self.admin)
        self.assertStatus(response, 400)
        self.assertStillPending()

    def test_new_password_must_differ_from_the_current_one(self):
        self.assertFieldErrors(self.change_password(self.TEMPORARY, self.TEMPORARY), "newPassword")
        self.assertStillPending()

    def test_new_password_must_meet_the_policy(self):
        for weak in ("Ab1", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere", "Aa1" + "x" * 70,
                     None, 12345678):
            with self.subTest(newPassword=weak):
                self.assertFieldErrors(self.change_password(self.TEMPORARY, weak), "newPassword")
        self.assertStillPending()

    def test_update_password_requires_authentication(self):
        response = self.client.put(
            UPDATE_PASSWORD,
            {"currentPassword": self.TEMPORARY, "newPassword": self.NEW},
            content_type="application/json",
        )
        self.assertStatus(response, 401)
        self.assertStillPending()

    def test_changing_the_password_unlocks_the_account(self):
        login = self.api_login(self.admin.email, self.TEMPORARY)
        self.assertStatus(login, 200)
        self.assertIs(login.json()["user"]["mustChangePassword"], True)
        first_token = login.json()["token"]
        self.assertPasswordChangeRequired(self.api_get(USERS, token=first_token))

        response = self.change_password(self.TEMPORARY, self.NEW, token=first_token)
        self.assertStatus(response, 200)
        body = response.json()
        self.assertIs(body["user"]["mustChangePassword"], False)
        new_token = body["token"]

        self.admin.refresh_from_db()
        self.assertFalse(self.admin.must_change_password)
        self.assertTrue(self.admin.check_password(self.NEW))
        self.assertFalse(self.admin.check_password(self.TEMPORARY))

        # The new token reaches the endpoints that were blocked.
        self.assertStatus(self.api_get(USERS, token=new_token), 200)
        self.assertStatus(self.api_get(COHORTS, token=new_token), 200)
        created = self.api_post(
            USERS,
            {"name": "New Educator", "email": unique_email("edu"), "role": "educator",
             "password": PASSWORD},
            token=new_token,
        )
        self.assertStatus(created, 201)
        self.assertStatus(self.api_put(UPDATE_DETAILS, {"name": "Settled Admin"}, token=new_token), 200)

        # Only the new password signs in now.
        self.assertStatus(self.api_login(self.admin.email, self.TEMPORARY), 401)
        relogin = self.api_login(self.admin.email, self.NEW)
        self.assertStatus(relogin, 200)
        self.assertIs(relogin.json()["user"]["mustChangePassword"], False)

    def test_a_temporary_password_session_does_not_survive_the_owners_change(self):
        # Someone who saw the temporary password signs in first...
        intruder = self.api_login(self.admin.email, self.TEMPORARY).json()["token"]
        # ...then the real owner signs in and sets their own password.
        owner = self.api_login(self.admin.email, self.TEMPORARY).json()["token"]
        self.assertStatus(self.change_password(self.TEMPORARY, self.NEW, token=owner), 200)
        # The intruder's limited session must not turn into a full one.
        self.assertStatus(self.api_get(ME, token=intruder), 401)
        self.assertStatus(self.api_get(USERS, token=intruder), 401)

    def test_users_without_a_pending_change_can_also_change_their_password(self):
        educator = make_user(self.institution, "educator")
        response = self.change_password(PASSWORD, self.NEW, user=educator)
        self.assertStatus(response, 200)
        self.assertIs(response.json()["user"]["mustChangePassword"], False)
        self.assertStatus(self.api_login(educator.email, self.NEW), 200)
        self.assertStatus(self.api_login(educator.email, PASSWORD), 401)


# --------------------------------------------------------------------------- #
# Profile updates                                                              #
# --------------------------------------------------------------------------- #


class UpdateDetailsTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.cohort = make_cohort(self.institution)
        self.user = make_user(self.institution, "student", cohort=self.cohort, name="Old Name")

    def update(self, body, user=None):
        return self.api_put(UPDATE_DETAILS, body, user=user or self.user)

    def test_updates_name_and_email(self):
        new_email = unique_email("renamed")
        response = self.update({"name": "  New Name  ", "email": f"  {new_email.upper()} "})
        self.assertStatus(response, 200)
        self.assertEqual(response.json()["user"]["name"], "New Name")
        self.assertEqual(response.json()["user"]["email"], new_email)

        self.user.refresh_from_db()
        self.assertEqual((self.user.name, self.user.email), ("New Name", new_email))
        self.assertStatus(self.api_login(new_email, PASSWORD), 200)

    def test_partial_update_keeps_other_fields(self):
        original_email = self.user.email
        self.assertStatus(self.update({"name": "Only Name"}), 200)
        self.user.refresh_from_db()
        self.assertEqual((self.user.name, self.user.email), ("Only Name", original_email))

    def test_email_taken_in_the_same_institution_is_rejected(self):
        other = make_user(self.institution, "educator")
        response = self.update({"email": other.email.upper()})
        self.assertStatus(response, 400)
        self.assertEqual(response.json()["message"], "Email already exists")
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.email, other.email)

    def test_email_taken_in_another_institution_is_rejected(self):
        outsider = make_user(make_institution(), "admin")
        response = self.update({"email": outsider.email})
        self.assertStatus(response, 400)
        self.assertEqual(response.json()["message"], "Email already exists")
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.email, outsider.email)

    def test_email_taken_by_a_concurrent_request_is_still_rejected(self):
        """If another request claims the email between the check and the save,
        the unique index must turn it into the same 400, not a 500."""
        other = make_user(self.institution, "educator")
        with mock.patch("django.db.models.query.QuerySet.exists", return_value=False):
            response = self.update({"email": other.email})
        self.assertStatus(response, 400)
        self.assertEqual(response.json()["message"], "Email already exists")
        self.assertEqual(User.objects.filter(email=other.email).count(), 1)

    def test_keeping_own_email_in_another_case_is_fine(self):
        original = self.user.email
        self.assertStatus(self.update({"email": original.upper()}), 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, original)

    def test_validation_errors(self):
        cases = [
            ({"name": "A"}, ["name"]),
            ({"name": "   "}, ["name"]),
            ({"name": "x" * 51}, ["name"]),
            ({"email": "not-an-email"}, ["email"]),
            ({"email": ""}, ["email"]),
            ({"name": "", "email": "nope"}, ["name", "email"]),
        ]
        for body, fields in cases:
            with self.subTest(body=body):
                self.assertFieldErrors(self.update(body), *fields)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "Old Name")

    def test_cannot_change_role_tenant_cohort_or_flags(self):
        other = make_institution()
        other_cohort = make_cohort(other)
        response = self.update(
            {
                "name": "Still Student",
                "role": "admin",
                "institution": str(other.pk),
                "institutionId": str(other.pk),
                "cohort": str(other_cohort.pk),
                "cohortId": str(other_cohort.pk),
                "mustChangePassword": True,
                "isEmailVerified": True,
            }
        )
        self.assertStatus(response, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "Still Student")
        self.assertEqual(self.user.role, "student")
        self.assertEqual(self.user.institution_id, self.institution.pk)
        self.assertEqual(self.user.cohort_id, self.cohort.pk)
        self.assertFalse(self.user.must_change_password)
        self.assertFalse(self.user.is_email_verified)

    def test_requires_authentication(self):
        response = self.client.put(UPDATE_DETAILS, {"name": "Anon"}, content_type="application/json")
        self.assertStatus(response, 401)

    def test_malformed_json_is_400(self):
        self.assertStatus(self.api_put(UPDATE_DETAILS, raw="{oops", user=self.user), 400)


# --------------------------------------------------------------------------- #
# Other endpoints behind the same guard                                       #
# --------------------------------------------------------------------------- #


class InterviewSessionTenancyTests(ApiTestCase):
    def test_requires_authentication(self):
        self.assertStatus(self.client.post(AI_SESSION), 401)
        self.assertFalse(InterviewSession.objects.exists())

    def test_session_is_stamped_with_the_callers_institution(self):
        mine = make_institution()
        make_institution()  # another tenant that must not be used
        student = make_user(mine, "student", cohort=make_cohort(mine))
        self.assertStatus(self.api_post(AI_SESSION, user=student), 200)
        session = InterviewSession.objects.get()
        self.assertEqual(session.institution_id, mine.pk)
        self.assertEqual(session.user_id, student.pk)
