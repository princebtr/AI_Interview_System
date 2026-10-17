"""Tests for institution administration: adding/listing members and cohorts.

Every request is scoped to the caller's institution; most tests set up a
second institution to prove nothing leaks across tenants.
"""
from datetime import timedelta
from unittest import mock

import bcrypt
from bson import ObjectId
from django.conf import settings
from django.utils import timezone

from accounts.models import User
from accounts.tests import (
    COHORTS,
    PASSWORD,
    USERS,
    ApiTestCase,
    bcrypt_cost,
    make_cohort,
    make_institution,
    make_user,
    unique_email,
)
from institutions.models import Cohort

# --------------------------------------------------------------------------- #
# Role-based access                                                            #
# --------------------------------------------------------------------------- #


class UsersEndpointAccessTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.cohort = make_cohort(self.institution)
        self.admin = make_user(self.institution, "admin")
        self.educator = make_user(self.institution, "educator")
        self.student = make_user(self.institution, "student", cohort=self.cohort)

    def new_user(self):
        return {"name": "New Educator", "email": unique_email("new"), "role": "educator",
                "password": PASSWORD}

    def test_unauthenticated_requests_are_401(self):
        self.assertStatus(self.api_get(USERS), 401)
        self.assertStatus(self.api_post(USERS, self.new_user()), 401)
        self.assertEqual(User.objects.count(), 3)

    def test_students_and_educators_are_forbidden(self):
        for user in (self.student, self.educator):
            with self.subTest(role=user.role, method="GET"):
                response = self.api_get(USERS, user=user)
                self.assertStatus(response, 403)
                self.assertNotIn("users", response.json())
            with self.subTest(role=user.role, method="POST"):
                self.assertStatus(self.api_post(USERS, self.new_user(), user=user), 403)
        self.assertEqual(User.objects.count(), 3)

    def test_admin_is_allowed(self):
        self.assertStatus(self.api_get(USERS, user=self.admin), 200)
        self.assertStatus(self.api_post(USERS, self.new_user(), user=self.admin), 201)

    def test_other_methods_are_not_allowed(self):
        for method in ("PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self.assertStatus(self.request(method, USERS, {}, user=self.admin), 405)


class CohortsEndpointAccessTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.cohort = make_cohort(self.institution, "CSE 2027")
        self.admin = make_user(self.institution, "admin")
        self.educator = make_user(self.institution, "educator")
        self.student = make_user(self.institution, "student", cohort=self.cohort)

    def test_unauthenticated_requests_are_401(self):
        self.assertStatus(self.api_get(COHORTS), 401)
        self.assertStatus(self.api_post(COHORTS, {"name": "ECE 2027"}), 401)
        self.assertEqual(Cohort.objects.count(), 1)

    def test_students_are_forbidden(self):
        self.assertStatus(self.api_get(COHORTS, user=self.student), 403)
        self.assertStatus(self.api_post(COHORTS, {"name": "ECE 2027"}, user=self.student), 403)
        self.assertEqual(Cohort.objects.count(), 1)

    def test_educators_can_list_but_not_create(self):
        response = self.api_get(COHORTS, user=self.educator)
        self.assertStatus(response, 200)
        self.assertEqual([c["name"] for c in response.json()["cohorts"]], ["CSE 2027"])

        self.assertStatus(self.api_post(COHORTS, {"name": "ECE 2027"}, user=self.educator), 403)
        self.assertEqual(Cohort.objects.count(), 1)

    def test_admins_can_list_and_create(self):
        self.assertStatus(self.api_get(COHORTS, user=self.admin), 200)
        self.assertStatus(self.api_post(COHORTS, {"name": "ECE 2027"}, user=self.admin), 201)
        self.assertEqual(Cohort.objects.count(), 2)


# --------------------------------------------------------------------------- #
# Adding users                                                                 #
# --------------------------------------------------------------------------- #


class CreateUserTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution(name="Springfield College")
        self.cohort = make_cohort(self.institution, "CSE 2027")
        self.admin = make_user(self.institution, "admin")
        self.other_institution = make_institution(name="Shelbyville High", type="school")
        self.other_cohort = make_cohort(self.other_institution, "Grade 10")

    def body(self, **overrides):
        data = {"name": "Asha Rao", "email": unique_email("asha"), "role": "educator",
                "password": PASSWORD}
        data.update(overrides)
        return data

    def create(self, as_user=None, **overrides):
        return self.api_post(USERS, self.body(**overrides), user=as_user or self.admin)

    def test_admin_can_add_an_admin_an_educator_and_a_student(self):
        for role in ("admin", "educator", "student"):
            with self.subTest(role=role):
                email = unique_email(role)
                extra = {"cohortId": str(self.cohort.pk)} if role == "student" else {}
                response = self.create(role=role, email=email, name=f"New {role.title()}", **extra)
                self.assertStatus(response, 201)
                body = response.json()
                self.assertIs(body["success"], True)
                created = body["user"]
                self.assertEqual(created["role"], role)
                self.assertEqual(created["email"], email)
                self.assertEqual(created["name"], f"New {role.title()}")
                self.assertIs(created["mustChangePassword"], True)
                self.assertNotIn("password", created)

                user = User.objects.get(email=email)
                self.assertEqual(created["id"], str(user.pk))
                self.assertEqual(user.institution_id, self.institution.pk)
                self.assertEqual(user.role, role)
                self.assertTrue(user.must_change_password)
                if role == "student":
                    self.assertEqual(user.cohort_id, self.cohort.pk)
                    self.assertEqual(created["cohort"], {"id": str(self.cohort.pk), "name": "CSE 2027"})
                else:
                    self.assertIsNone(user.cohort_id)
                    self.assertIsNone(created["cohort"])

    def test_student_without_a_cohort_is_rejected(self):
        email = unique_email("stu")
        self.assertFieldErrors(self.create(role="student", email=email), "cohortId")
        self.assertFalse(User.objects.filter(email=email).exists())

    def test_student_with_a_malformed_cohort_id_is_400_not_500(self):
        for bad in ("nope", "", "   ", 123, None, ["x"], {"id": "x"}, str(ObjectId())):
            with self.subTest(cohortId=bad):
                self.assertFieldErrors(self.create(role="student", cohortId=bad), "cohortId")
        self.assertFalse(User.objects.filter(role="student").exists())

    def test_student_cannot_join_another_institutions_cohort(self):
        email = unique_email("crossover")
        response = self.create(role="student", email=email, cohortId=str(self.other_cohort.pk))
        self.assertFieldErrors(response, "cohortId")
        self.assertFalse(User.objects.filter(email=email).exists())

        # ...and the other tenant's admin can't use ours either.
        other_admin = make_user(self.other_institution, "admin")
        response = self.create(as_user=other_admin, role="student", email=email,
                               cohortId=str(self.cohort.pk))
        self.assertFieldErrors(response, "cohortId")
        self.assertFalse(User.objects.filter(email=email).exists())

    def test_staff_ignore_cohort_id(self):
        cases = [("educator", self.cohort), ("admin", self.cohort), ("educator", self.other_cohort)]
        for role, cohort in cases:
            with self.subTest(role=role, cohort=cohort.name):
                email = unique_email(role)
                response = self.create(role=role, email=email, cohortId=str(cohort.pk))
                self.assertStatus(response, 201)
                self.assertIsNone(response.json()["user"]["cohort"])
                self.assertIsNone(User.objects.get(email=email).cohort_id)

    def test_email_and_name_are_normalised(self):
        response = self.create(email="  Mixed.Case@Example.EDU  ", name="  Asha Rao  ")
        self.assertStatus(response, 201)
        self.assertEqual(response.json()["user"]["email"], "mixed.case@example.edu")
        user = User.objects.get(email="mixed.case@example.edu")
        self.assertEqual(user.name, "Asha Rao")

    def test_duplicate_email_is_rejected_whatever_the_case_or_tenant(self):
        here = make_user(self.institution, "educator")
        elsewhere = make_user(self.other_institution, "student", cohort=self.other_cohort)
        for email in (here.email, here.email.upper(), f"  {elsewhere.email.title()} "):
            with self.subTest(email=email):
                self.assertFieldErrors(self.create(email=email), "email")
        self.assertEqual(User.objects.count(), 3)

    def test_email_claimed_by_a_concurrent_request_is_still_a_400(self):
        """If another request takes the email between the duplicate check and
        the save, the unique index must produce the same 400, not a 500."""
        existing = make_user(self.other_institution, "educator")
        with mock.patch("django.db.models.query.QuerySet.exists", return_value=False):
            response = self.create(email=existing.email)
        self.assertFieldErrors(response, "email")
        self.assertEqual(User.objects.filter(email=existing.email).count(), 1)

    def test_all_validation_errors_are_reported_together(self):
        response = self.api_post(
            USERS,
            {"name": "A", "email": "not-an-email", "role": "superuser", "password": "weak"},
            user=self.admin,
        )
        body = self.assertFieldErrors(response, "name", "email", "role", "password")
        self.assertEqual(body["message"], body["errors"][0]["message"])

        response = self.api_post(
            USERS, {"name": "", "email": "x", "role": "student", "password": ""}, user=self.admin
        )
        self.assertFieldErrors(response, "name", "email", "password", "cohortId")
        self.assertEqual(User.objects.count(), 1)

    def test_role_must_be_admin_educator_or_student(self):
        for role in (None, "", "Student", "ADMIN", "superadmin", "user", ["admin"], {"r": 1}, 1):
            with self.subTest(role=role):
                self.assertFieldErrors(self.create(role=role), "role")
        body = self.body()
        del body["role"]
        self.assertFieldErrors(self.api_post(USERS, body, user=self.admin), "role")
        self.assertEqual(User.objects.count(), 1)

    def test_password_policy_is_enforced(self):
        weak_passwords = [
            "", "Ab1", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere",
            "Aa1" + "x" * 70,   # 73 bytes: bcrypt would silently truncate it
            "Aa1" + "é" * 35,   # 38 characters but 73 bytes
            12345678, None,
        ]
        for password in weak_passwords:
            with self.subTest(password=password):
                self.assertFieldErrors(self.create(password=password), "password")
        self.assertEqual(User.objects.count(), 1)

    def test_require_password_change_defaults_to_true(self):
        email = unique_email("default")
        self.assertStatus(self.create(email=email), 201)
        self.assertTrue(User.objects.get(email=email).must_change_password)

    def test_require_password_change_false_is_respected(self):
        email = unique_email("ready")
        response = self.create(email=email, requirePasswordChange=False)
        self.assertStatus(response, 201)
        self.assertIs(response.json()["user"]["mustChangePassword"], False)
        user = User.objects.get(email=email)
        self.assertFalse(user.must_change_password)

        # They can use protected endpoints straight away.
        login = self.api_login(email, PASSWORD)
        self.assertStatus(login, 200)
        self.assertStatus(self.api_get(COHORTS, token=login.json()["token"]), 200)

    def test_require_password_change_must_be_a_boolean(self):
        for value in ("false", "true", 0, 1, None, "no"):
            with self.subTest(requirePasswordChange=value):
                self.assertFieldErrors(self.create(requirePasswordChange=value),
                                       "requirePasswordChange")
        self.assertEqual(User.objects.count(), 1)

    def test_password_is_bcrypt_hashed_and_works_for_login(self):
        email, raw = unique_email("hashed"), "Sup3rSecret"
        response = self.create(email=email, password=raw, role="educator")
        self.assertStatus(response, 201)

        user = User.objects.get(email=email)
        self.assertNotEqual(user.password, raw)
        self.assertNotIn(raw, user.password)
        self.assertRegex(user.password, r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")
        self.assertEqual(bcrypt_cost(user.password), settings.BCRYPT_ROUNDS)
        self.assertTrue(bcrypt.checkpw(raw.encode(), user.password.encode()))
        self.assertNotIn(user.password, response.content.decode())

        login = self.api_login(email, raw)
        self.assertStatus(login, 200)
        signed_in = login.json()["user"]
        self.assertEqual(signed_in["role"], "educator")
        self.assertEqual(signed_in["institution"]["id"], str(self.institution.pk))
        self.assertIs(signed_in["mustChangePassword"], True)

    def test_institution_in_the_body_is_ignored(self):
        email = unique_email("tenant")
        target = str(self.other_institution.pk)
        response = self.create(
            email=email, institution=target, institutionId=target, institution_id=target,
            isEmailVerified=True, mustChangePassword=False,
        )
        self.assertStatus(response, 201)
        user = User.objects.get(email=email)
        self.assertEqual(user.institution_id, self.institution.pk)
        self.assertFalse(user.is_email_verified)
        self.assertTrue(user.must_change_password)

        other_admin = make_user(self.other_institution, "admin")
        listed = self.api_get(USERS, user=other_admin).json()["users"]
        self.assertNotIn(email, [u["email"] for u in listed])

    def test_malformed_body_is_400(self):
        for raw in ("{oops", "[]", "null", '"text"'):
            with self.subTest(raw=raw):
                self.assertStatus(self.api_post(USERS, raw=raw, user=self.admin), 400)
        self.assertEqual(User.objects.count(), 1)


# --------------------------------------------------------------------------- #
# Listing users                                                                #
# --------------------------------------------------------------------------- #


class ListUsersTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.cse = make_cohort(self.institution, "CSE 2027")
        self.ece = make_cohort(self.institution, "ECE 2027")
        self.admin = make_user(self.institution, "admin", name="Asha Admin")
        self.educators = [
            make_user(self.institution, "educator", name="Priya Teacher"),
            make_user(self.institution, "educator", name="Karan Teacher"),
        ]
        self.students = [
            make_user(self.institution, "student", cohort=self.cse, name="Ravi Kumar"),
            make_user(self.institution, "student", cohort=self.cse, name="Meera Nair"),
            make_user(self.institution, "student", cohort=self.ece, name="John Doe",
                      email=unique_email("jdoe", "springfield.edu")),
        ]
        self.members = [self.admin, *self.educators, *self.students]

        self.other = make_institution()
        self.other_cohort = make_cohort(self.other, "CSE 2027")
        self.outsiders = [
            make_user(self.other, "admin", name="Other Admin"),
            make_user(self.other, "student", cohort=self.other_cohort, name="Ravi Outsider"),
            make_user(self.other, "student", cohort=self.other_cohort, name="Zed Outsider",
                      email=unique_email("zed", "springfield.edu")),
        ]

    def list(self, as_user=None, **params):
        return self.api_get(USERS, params=params, user=as_user or self.admin)

    def ids(self, response):
        self.assertStatus(response, 200)
        return [u["id"] for u in response.json()["users"]]

    @staticmethod
    def id_set(users):
        return {str(u.pk) for u in users}

    def stamp_creation_order(self, newest_first):
        """Give members distinct, known creation times (newest first)."""
        base = timezone.now() - timedelta(days=1)
        for age, user in enumerate(newest_first):
            User.objects.filter(pk=user.pk).update(created_at=base - timedelta(minutes=age))

    def test_lists_only_the_admins_institution(self):
        response = self.list()
        self.assertEqual(set(self.ids(response)), self.id_set(self.members))
        self.assertEqual(response.json()["total"], len(self.members))

        response = self.list(as_user=self.outsiders[0])
        self.assertEqual(set(self.ids(response)), self.id_set(self.outsiders))
        self.assertEqual(response.json()["counts"], {"admin": 1, "educator": 0, "student": 2})

    def test_counts_cover_the_whole_institution_whatever_the_filter(self):
        expected = {"admin": 1, "educator": 2, "student": 3}
        for params in ({}, {"role": "student"}, {"q": "Ravi"}, {"cohort": str(self.cse.pk)},
                       {"limit": 1}):
            with self.subTest(params=params):
                response = self.list(**params)
                self.assertStatus(response, 200)
                self.assertEqual(response.json()["counts"], expected)

    def test_filter_by_role(self):
        for role, users in (("student", self.students), ("educator", self.educators),
                            ("admin", [self.admin])):
            with self.subTest(role=role):
                response = self.list(role=role)
                self.assertEqual(set(self.ids(response)), self.id_set(users))
                self.assertEqual(response.json()["total"], len(users))

    def test_unknown_role_filter_is_400(self):
        for role in ("superuser", "Student", "user"):
            with self.subTest(role=role):
                self.assertStatus(self.list(role=role), 400)

    def test_filter_by_own_cohort(self):
        response = self.list(cohort=str(self.cse.pk))
        self.assertEqual(set(self.ids(response)), self.id_set(self.students[:2]))
        for entry in response.json()["users"]:
            self.assertEqual(entry["cohort"], {"id": str(self.cse.pk), "name": "CSE 2027"})

        response = self.list(cohort=str(self.ece.pk), role="student")
        self.assertEqual(self.ids(response), [str(self.students[2].pk)])

    def test_cohort_filter_rejects_other_tenants_and_malformed_ids(self):
        for value in (str(self.other_cohort.pk), "nope", "(", str(ObjectId())):
            with self.subTest(cohort=value):
                response = self.list(cohort=value)
                self.assertStatus(response, 400)
                self.assertNotIn("users", response.json())

    def test_search_matches_name_or_email_case_insensitively(self):
        cases = [
            ("ravi", [self.students[0]]),          # not "Ravi Outsider" from the other tenant
            ("MEERA", [self.students[1]]),
            ("teacher", self.educators),
            ("SPRINGFIELD.EDU", [self.students[2]]),  # matches the email only
            (self.students[2].email.split("@")[0].upper(), [self.students[2]]),
            ("outsider", []),
            ("no such person", []),
        ]
        for query, users in cases:
            with self.subTest(q=query):
                response = self.list(q=query)
                self.assertEqual(set(self.ids(response)), self.id_set(users))
                self.assertEqual(response.json()["total"], len(users))

    def test_search_treats_regex_metacharacters_literally(self):
        for name in ("J. Smith", "JX Smith", "Ann (TA)", "Star* Pupil", "Plus+ One",
                     "Why? Me", "Brack[et] Kid", "Curly{2} Kid", "Back\\slash Kid",
                     "Caret^ Kid", "Dollar$ Kid", "Pipe| Kid", "Glob .* Kid"):
            make_user(self.institution, "educator", name=name)
        everyone = list(User.objects.filter(institution=self.institution))

        for query in ("J. S", ".*", ".", "(", ")", "(TA)", "*", "+", "?", "[", "]", "[et]",
                      "{2}", "\\", "^", "$", "|", "a.b"):
            expected = {
                str(u.pk) for u in everyone
                if query.lower() in u.name.lower() or query.lower() in u.email.lower()
            }
            with self.subTest(q=query):
                response = self.list(q=query, limit=200)
                self.assertEqual(set(self.ids(response)), expected)
                self.assertEqual(response.json()["total"], len(expected))

    def test_search_with_a_nul_byte_does_not_crash(self):
        response = self.list(q="ra\x00vi")
        self.assertIn(response.status_code, (200, 400), response.content[:300])
        if response.status_code == 200:
            self.assertEqual(response.json()["users"], [])

    def test_newest_members_come_first(self):
        order = [self.students[1], self.admin, self.educators[0], self.students[2],
                 self.educators[1], self.students[0]]
        self.stamp_creation_order(order)
        self.assertEqual(self.ids(self.list()), [str(u.pk) for u in order])

    def test_pagination(self):
        order = [self.students[2], self.students[1], self.students[0], self.educators[1],
                 self.educators[0], self.admin]
        self.stamp_creation_order(order)
        pages = []
        for offset in (0, 2, 4, 6):
            with self.subTest(offset=offset):
                response = self.list(limit=2, offset=offset)
                self.assertEqual(response.json()["total"], 6)
                pages.append(self.ids(response))
        self.assertEqual(pages, [[str(u.pk) for u in order[i:i + 2]] for i in (0, 2, 4)] + [[]])

        # A filter's total counts every match, not just the page.
        response = self.list(role="student", limit=1, offset=1)
        self.assertEqual(self.ids(response), [str(self.students[1].pk)])
        self.assertEqual(response.json()["total"], 3)

    def test_page_size_is_clamped_and_garbage_falls_back_to_defaults(self):
        User.objects.bulk_create(
            User(institution=self.institution, cohort=self.cse, role="student",
                 name=f"Bulk Student {i:03d}", email=unique_email(f"bulk{i}"), password="!")
            for i in range(200)
        )
        total = len(self.members) + 200
        cases = [
            ({}, 50),
            ({"limit": 1000}, 200),
            ({"limit": 200}, 200),
            ({"limit": 0}, 1),
            ({"limit": -3}, 1),
            ({"limit": "abc"}, 50),
            ({"limit": 10, "offset": -5}, 10),
            ({"limit": 10, "offset": "abc"}, 10),
            ({"limit": 1000, "offset": 200}, total - 200),
        ]
        for params, size in cases:
            with self.subTest(params=params):
                response = self.list(**params)
                self.assertEqual(len(self.ids(response)), size)
                self.assertEqual(response.json()["total"], total)

    def test_absurd_offset_does_not_crash(self):
        response = self.list(offset=10 ** 20)
        self.assertIn(response.status_code, (200, 400), response.content[:300])
        if response.status_code == 200:
            self.assertEqual(response.json()["users"], [])
            self.assertEqual(response.json()["total"], len(self.members))

    def test_entries_have_the_expected_shape_and_no_secrets(self):
        response = self.list()
        self.assertStatus(response, 200)
        for entry in response.json()["users"]:
            self.assertEqual(
                set(entry),
                {"id", "name", "email", "role", "cohort", "mustChangePassword", "lastLogin",
                 "createdAt"},
            )
        content = response.content.decode()
        for user in self.members:
            self.assertNotIn(user.password, content)

        john = next(u for u in response.json()["users"] if u["id"] == str(self.students[2].pk))
        self.assertEqual(john["cohort"], {"id": str(self.ece.pk), "name": "ECE 2027"})
        self.assertEqual(john["name"], "John Doe")
        self.assertEqual(john["role"], "student")


# --------------------------------------------------------------------------- #
# Cohorts                                                                      #
# --------------------------------------------------------------------------- #


class CohortTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.admin = make_user(self.institution, "admin")
        self.educator = make_user(self.institution, "educator")
        self.other = make_institution()
        self.other_admin = make_user(self.other, "admin")

    def create(self, name, as_user=None):
        return self.api_post(COHORTS, {"name": name}, user=as_user or self.admin)

    def listed(self, as_user=None):
        response = self.api_get(COHORTS, user=as_user or self.admin)
        self.assertStatus(response, 200)
        return response.json()["cohorts"]

    def test_create_trims_and_collapses_whitespace(self):
        response = self.create("  CSE \t  2027  ")
        self.assertStatus(response, 201)
        cohort = response.json()["cohort"]
        self.assertEqual(cohort["name"], "CSE 2027")
        self.assertEqual(cohort["studentCount"], 0)

        saved = Cohort.objects.get(pk=cohort["id"])
        self.assertEqual(saved.name, "CSE 2027")
        self.assertEqual(saved.institution_id, self.institution.pk)

    def test_duplicates_differing_only_by_case_or_spacing_are_rejected(self):
        self.assertStatus(self.create("CSE 2027"), 201)
        for variant in ("CSE 2027", "cse 2027", "  Cse   2027 ", "CSE\t2027", "cSe\n2027"):
            with self.subTest(name=variant):
                self.assertFieldErrors(self.create(variant), "name")
        self.assertEqual(Cohort.objects.count(), 1)

    def test_duplicate_created_by_a_concurrent_request_is_still_a_400(self):
        """The unique (institution, name_key) index backs up the pre-check."""
        self.assertStatus(self.create("CSE 2027"), 201)
        with mock.patch("django.db.models.query.QuerySet.exists", return_value=False):
            response = self.create("cse  2027")
        self.assertFieldErrors(response, "name")
        self.assertEqual(Cohort.objects.count(), 1)

    def test_institution_in_the_body_is_ignored(self):
        response = self.api_post(
            COHORTS,
            {"name": "CSE 2027", "institution": str(self.other.pk),
             "institutionId": str(self.other.pk)},
            user=self.admin,
        )
        self.assertStatus(response, 201)
        cohort = Cohort.objects.get(pk=response.json()["cohort"]["id"])
        self.assertEqual(cohort.institution_id, self.institution.pk)
        self.assertEqual(self.listed(as_user=self.other_admin), [])

    def test_regex_metacharacters_are_literal(self):
        names = ["CSE 2027", "CSE.2027", "CSE (2027)", "CSE*", "CSE+", "CSE?", "CSE[1]", "C$E",
                 "^CSE", "CSE|ECE", "CSE\\2027", "CSE.*"]
        for name in names:
            with self.subTest(name=name):
                self.assertStatus(self.create(name), 201)
        self.assertEqual(sorted(c["name"] for c in self.listed()), sorted(names))

        for duplicate in ("cse.2027", "cse (2027)", "Cse.*"):
            with self.subTest(duplicate=duplicate):
                self.assertFieldErrors(self.create(duplicate), "name")
        self.assertEqual(Cohort.objects.count(), len(names))

    def test_name_is_required_and_at_most_60_characters(self):
        for bad in ("", "   ", None, 123, ["CSE"], "x" * 61, " ".join(["ab"] * 21)):
            with self.subTest(name=bad):
                self.assertFieldErrors(self.create(bad), "name")
        self.assertFieldErrors(self.api_post(COHORTS, {}, user=self.admin), "name")
        self.assertFalse(Cohort.objects.exists())

        self.assertStatus(self.create("x" * 60), 201)
        # Length is measured after whitespace is collapsed.
        response = self.create("  " + "y" * 30 + "      " + "z" * 29 + "  ")
        self.assertStatus(response, 201)
        self.assertEqual(len(response.json()["cohort"]["name"]), 60)

    def test_list_shows_own_cohorts_with_student_counts(self):
        cse = make_cohort(self.institution, "CSE 2027")
        ece = make_cohort(self.institution, "ECE 2027")
        arts = make_cohort(self.institution, "arts 2026")
        for _ in range(2):
            make_user(self.institution, "student", cohort=cse)
        make_user(self.institution, "student", cohort=ece)
        theirs = make_cohort(self.other, "CSE 2027")
        for _ in range(3):
            make_user(self.other, "student", cohort=theirs)

        expected = [
            {"id": str(arts.pk), "name": "arts 2026", "studentCount": 0},
            {"id": str(cse.pk), "name": "CSE 2027", "studentCount": 2},
            {"id": str(ece.pk), "name": "ECE 2027", "studentCount": 1},
        ]
        listed = [{k: c[k] for k in ("id", "name", "studentCount")} for c in self.listed()]
        self.assertEqual(listed, expected)
        as_educator = [{k: c[k] for k in ("id", "name", "studentCount")} for c in self.listed(as_user=self.educator)]
        self.assertEqual(as_educator, expected)
        self.assertEqual(
            [{k: c[k] for k in ("id", "name", "studentCount")} for c in self.listed(as_user=self.other_admin)],
            [{"id": str(theirs.pk), "name": "CSE 2027", "studentCount": 3}],
        )

    def test_same_name_may_exist_in_two_institutions(self):
        mine = self.create("CSE 2027")
        theirs = self.create("cse 2027", as_user=self.other_admin)
        self.assertStatus(mine, 201)
        self.assertStatus(theirs, 201)
        self.assertEqual([c["id"] for c in self.listed()], [mine.json()["cohort"]["id"]])
        self.assertEqual([c["id"] for c in self.listed(as_user=self.other_admin)],
                         [theirs.json()["cohort"]["id"]])

    def test_list_is_sorted_case_insensitively(self):
        for name in ("beta", "Alpha", "gamma", "Delta"):
            self.assertStatus(self.create(name), 201)
        self.assertEqual([c["name"] for c in self.listed()], ["Alpha", "beta", "Delta", "gamma"])

    def test_malformed_body_is_400(self):
        for raw in ("{oops", "[]"):
            with self.subTest(raw=raw):
                self.assertStatus(self.api_post(COHORTS, raw=raw, user=self.admin), 400)
        self.assertFalse(Cohort.objects.exists())

    def test_new_cohort_can_take_students_right_away(self):
        cohort_id = self.create("CSE 2027").json()["cohort"]["id"]
        response = self.api_post(
            USERS,
            {"name": "Ravi Kumar", "email": unique_email("ravi"), "role": "student",
             "password": PASSWORD, "cohortId": cohort_id},
            user=self.admin,
        )
        self.assertStatus(response, 201)
        self.assertEqual(response.json()["user"]["cohort"]["id"], cohort_id)
        self.assertEqual(self.listed()[0]["studentCount"], 1)
