"""Tests for institution administration: adding/listing/moving members, the
academic structure (Batch -> Department -> Section -> Cohort), the overview and
CSV import.

Every request is scoped to the caller's institution; most tests set up a
second institution to prove nothing leaks across tenants.
"""
from datetime import timedelta
from unittest import mock

import bcrypt
from bson import ObjectId
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.models import User
from accounts.tests import (
    ME,
    PASSWORD,
    STRUCTURE,
    USERS,
    ApiTestCase,
    bcrypt_cost,
    make_batch,
    make_cohort,
    make_department,
    make_institution,
    make_section,
    make_user,
    unique_email,
)
from accounts.auth import create_token
from ai.models import PracticeAttempt
from assessments.models import Assessment
from institutions.models import MODELS, AuditLog, Batch, Cohort, Department, Section

OVERVIEW = "/api/institution/overview"
IMPORT = "/api/institution/users/import"

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


class StructureEndpointAccessTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.cohort = make_cohort(self.institution, "CSE 2027")
        self.batch = self.cohort.section.department.batch
        self.admin = make_user(self.institution, "admin")
        self.educator = make_user(self.institution, "educator")
        self.student = make_user(self.institution, "student", cohort=self.cohort)
        self.detail = node_url(self.batch)

    def test_unauthenticated_requests_are_401(self):
        self.assertStatus(self.api_get(STRUCTURE), 401)
        self.assertStatus(self.api_post(STRUCTURE, {"level": "batch", "name": "2028"}), 401)
        self.assertStatus(self.api_get(self.detail), 401)
        self.assertStatus(self.api_patch(self.detail, {"name": "Renamed"}), 401)
        self.assertStatus(self.api_delete(self.detail), 401)
        self.assertEqual(Batch.objects.count(), 1)

    def test_students_are_forbidden(self):
        self.assertStatus(self.api_get(STRUCTURE, user=self.student), 403)
        self.assertStatus(self.api_post(STRUCTURE, {"level": "batch", "name": "2028"}, user=self.student), 403)
        self.assertStatus(self.api_get(self.detail, user=self.student), 403)
        self.assertStatus(self.api_patch(self.detail, {"name": "Renamed"}, user=self.student), 403)
        self.assertStatus(self.api_delete(self.detail, user=self.student), 403)
        self.assertEqual(Batch.objects.count(), 1)

    def test_educators_can_read_but_not_change(self):
        response = self.api_get(STRUCTURE, user=self.educator)
        self.assertStatus(response, 200)
        self.assertEqual([b["id"] for b in response.json()["batches"]], [str(self.batch.pk)])
        self.assertStatus(self.api_get(self.detail, user=self.educator), 200)

        self.assertStatus(self.api_post(STRUCTURE, {"level": "batch", "name": "2028"}, user=self.educator), 403)
        self.assertStatus(
            self.api_post(STRUCTURE, {"level": "cohort", "name": "Lab", "parentId": str(self.cohort.section_id)},
                          user=self.educator),
            403,
        )
        self.assertStatus(self.api_patch(self.detail, {"name": "Renamed"}, user=self.educator), 403)
        empty = make_batch(self.institution, "Empty")
        self.assertStatus(self.api_delete(node_url(empty), user=self.educator), 403)
        self.assertEqual(Batch.objects.count(), 2)
        self.assertEqual(Cohort.objects.count(), 1)
        self.batch.refresh_from_db()
        self.assertNotEqual(self.batch.name, "Renamed")

    def test_admins_can_read_and_change(self):
        self.assertStatus(self.api_get(STRUCTURE, user=self.admin), 200)
        self.assertStatus(self.api_post(STRUCTURE, {"level": "batch", "name": "2028"}, user=self.admin), 201)
        self.assertEqual(Batch.objects.count(), 2)
        self.assertStatus(self.api_patch(self.detail, {"name": "Renamed"}, user=self.admin), 200)

    def test_other_methods_are_not_allowed(self):
        for method in ("PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self.assertStatus(self.request(method, STRUCTURE, {}, user=self.admin), 405)
        self.assertStatus(self.request("POST", self.detail, {}, user=self.admin), 405)
        self.assertStatus(self.request("PUT", self.detail, {}, user=self.admin), 405)

    def test_old_cohort_endpoints_are_gone(self):
        self.assertStatus(self.api_get("/api/institution/cohorts", user=self.admin), 404)
        self.assertStatus(self.api_get(f"/api/institution/cohorts/{self.cohort.pk}", user=self.admin), 404)


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
                    section = self.cohort.section
                    self.assertEqual(
                        (user.batch_id, user.department_id, user.section_id),
                        (section.department.batch_id, section.department_id, section.pk),
                    )
                    self.assertEqual(created["placement"]["cohort"], created["cohort"])
                    self.assertEqual(created["placement"]["label"], self.cohort.label)
                else:
                    self.assertIsNone(user.cohort_id)
                    self.assertIsNone(user.batch_id)
                    self.assertIsNone(created["cohort"])
                    self.assertIsNone(created["placement"])

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
                self.assertIsNone(User.objects.get(email=email).section_id)

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
        self.assertStatus(self.api_get(STRUCTURE, token=login.json()["token"]), 200)

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
                       {"department": str(self.cse.section.department_id)}, {"limit": 1}):
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

    def test_filter_by_any_level(self):
        # self.cse and self.ece each sit in their own batch. Build a shared tree.
        section = self.cse.section
        department = section.department
        batch = department.batch
        lab2 = make_cohort(self.institution, "Lab 2", section=section)
        section_b = make_section(department, "B")
        sibling_department = make_department(batch, "Mech")
        in_lab2 = make_user(self.institution, "student", cohort=lab2)
        in_b = make_user(self.institution, "student", cohort=make_cohort(self.institution, section=section_b))
        in_mech = make_user(self.institution, "student",
                            cohort=make_cohort(self.institution, section=make_section(sibling_department)))
        cse_students = self.students[:2]
        cases = [
            ({"batch": str(batch.pk)}, [*cse_students, in_lab2, in_b, in_mech]),
            ({"department": str(department.pk)}, [*cse_students, in_lab2, in_b]),
            ({"section": str(section.pk)}, [*cse_students, in_lab2]),
            ({"cohort": str(self.cse.pk)}, cse_students),
            ({"cohort": str(lab2.pk)}, [in_lab2]),
            ({"section": str(section_b.pk), "role": "student"}, [in_b]),
            ({"batch": str(batch.pk), "department": str(sibling_department.pk)}, [in_mech]),
            ({"department": str(sibling_department.pk), "cohort": str(self.cse.pk)}, []),
            ({"batch": str(self.ece.section.department.batch_id)}, [self.students[2]]),
            ({"batch": str(batch.pk), "q": "meera"}, [self.students[1]]),
        ]
        for params, expected in cases:
            with self.subTest(params=params):
                response = self.list(**params)
                self.assertEqual(set(self.ids(response)), self.id_set(expected))
                self.assertEqual(response.json()["total"], len(expected))

    def test_level_filters_reject_other_tenants_and_malformed_ids(self):
        theirs = self.other_cohort
        foreign = {
            "batch": theirs.section.department.batch_id,
            "department": theirs.section.department_id,
            "section": theirs.section_id,
            "cohort": theirs.pk,
        }
        for level, foreign_id in foreign.items():
            # The cohort's own id is the wrong level for batch/department/section.
            for value in (str(foreign_id), "nope", "(", str(ObjectId()), str(self.cse.pk) if level != "cohort" else "$"):
                with self.subTest(level=level, value=value):
                    response = self.list(**{level: value})
                    self.assertStatus(response, 400)
                    self.assertEqual(response.json()["message"], f"Unknown {level}")
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
        def bulk_student(i):
            user = User(institution=self.institution, role="student",
                        name=f"Bulk Student {i:03d}", email=unique_email(f"bulk{i}"), password="!")
            user.place(self.cse)
            return user

        User.objects.bulk_create(bulk_student(i) for i in range(200))
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
                {"id", "name", "email", "role", "cohort", "placement", "mustChangePassword",
                 "lastLogin", "createdAt"},
            )
        content = response.content.decode()
        for user in self.members:
            self.assertNotIn(user.password, content)

        john = next(u for u in response.json()["users"] if u["id"] == str(self.students[2].pk))
        self.assertEqual(john["cohort"], {"id": str(self.ece.pk), "name": "ECE 2027"})
        self.assertEqual(john["placement"]["cohort"], john["cohort"])
        self.assertEqual(john["placement"]["label"], self.ece.label)
        admin = next(u for u in response.json()["users"] if u["id"] == str(self.admin.pk))
        self.assertIsNone(admin["placement"])
        self.assertEqual(john["name"], "John Doe")
        self.assertEqual(john["role"], "student")


# --------------------------------------------------------------------------- #
# Academic structure: Batch -> Department -> Section -> Cohort                 #
# --------------------------------------------------------------------------- #


def node_url(node):
    return f"{STRUCTURE}/{node.LEVEL}/{node.pk}"


def make_chain(institution, *names):
    """batch, department, section, cohort with the given names (missing ones made up)."""
    names = [*names, None, None, None, None][:4]
    batch = make_batch(institution, names[0])
    department = make_department(batch, names[1])
    section = make_section(department, names[2])
    return batch, department, section, make_cohort(institution, names[3], section=section)


def make_test(institution, node):
    test = Assessment(
        institution=institution, title="T", starts_at=timezone.now() + timedelta(days=1),
        duration_minutes=30, marks_per_question=1, questions=[],
    )
    test.set_audience(node)
    test.save()
    return test


class StructureTestCase(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.admin = make_user(self.institution, "admin")
        self.educator = make_user(self.institution, "educator")
        self.other = make_institution()
        self.other_admin = make_user(self.other, "admin")

    def create(self, level, name, parent=None, as_user=None):
        body = {"level": level, "name": name}
        if parent is not None:
            body["parentId"] = parent if isinstance(parent, str) else str(parent.pk)
        return self.api_post(STRUCTURE, body, user=as_user or self.admin)

    def created(self, level, name, parent=None, as_user=None):
        response = self.create(level, name, parent, as_user)
        self.assertStatus(response, 201)
        return MODELS[level].objects.get(pk=response.json()["node"]["id"])

    def tree(self, as_user=None):
        response = self.api_get(STRUCTURE, user=as_user or self.admin)
        self.assertStatus(response, 200)
        return response.json()


class CreateGroupTests(StructureTestCase):
    def test_create_each_level(self):
        response = self.create("batch", "  2023 -\t 2027 ")
        self.assertStatus(response, 201)
        body = response.json()
        self.assertIs(body["success"], True)
        node = body["node"]
        batch = Batch.objects.get(pk=node["id"])
        self.assertEqual(batch.name, "2023 - 2027")
        self.assertEqual(batch.institution_id, self.institution.pk)
        self.assertEqual(
            {k: node[k] for k in ("level", "id", "name", "label", "path", "studentCount", "activated",
                                  "attempts", "practice30Days", "averageScore")},
            {"level": "batch", "id": str(batch.pk), "name": "2023 - 2027", "label": "2023 - 2027",
             "path": [{"level": "batch", "id": str(batch.pk), "name": "2023 - 2027"}],
             "studentCount": 0, "activated": 0, "attempts": 0, "practice30Days": 0, "averageScore": None},
        )
        self.assertIn("createdAt", node)

        parent, path = batch, node["path"]
        for level, name in (("department", "CSE"), ("section", "A"), ("cohort", "Lab 1")):
            with self.subTest(level=level):
                response = self.create(level, name, parent)
                self.assertStatus(response, 201)
                node = response.json()["node"]
                saved = MODELS[level].objects.get(pk=node["id"])
                self.assertEqual(saved.institution_id, self.institution.pk)
                self.assertEqual(saved.parent, parent)
                path = [*path, {"level": level, "id": node["id"], "name": name}]
                self.assertEqual((node["level"], node["name"], node["path"]), (level, name, path))
                self.assertEqual(node["label"], " · ".join(p["name"] for p in path))
                parent = saved

        tree = self.tree()
        self.assertEqual(tree["counts"], {"batches": 1, "departments": 1, "sections": 1, "cohorts": 1})
        cohort = tree["batches"][0]["children"][0]["children"][0]["children"][0]
        self.assertEqual((cohort["name"], cohort["label"]), ("Lab 1", "2023 - 2027 · CSE · A · Lab 1"))
        self.assertNotIn("children", cohort)
        self.assertEqual(AuditLog.objects.filter(institution=self.institution, action__endswith=".created").count(), 4)

    def test_duplicates_within_a_parent_are_rejected_but_other_parents_may_reuse_the_name(self):
        batch = self.created("batch", "2027")
        other_batch = self.created("batch", "2028")
        for variant in ("2027", " 2027 ", "2027\t"):
            with self.subTest(level="batch", name=variant):
                self.assertFieldErrors(self.create("batch", variant), "name")

        parents = {"department": (batch, other_batch)}
        cse = self.created("department", "CSE", batch)
        parents["section"] = (cse, self.created("department", "ECE", batch))
        section = self.created("section", "A", cse)
        parents["cohort"] = (section, self.created("section", "B", cse))

        for level, (first, second) in parents.items():
            name = {"department": "Computer Science", "section": "Morning", "cohort": "Lab 1"}[level]
            with self.subTest(level=level):
                self.created(level, name, first)
                for variant in (name, name.upper(), f"  {name.lower()}  ", name.replace(" ", "\n")):
                    self.assertFieldErrors(self.create(level, variant, first), "name")
                # The same name under a different parent is fine.
                self.created(level, name.lower(), second)
                self.assertEqual(MODELS[level].objects.filter(name_key=name.casefold()).count(), 2)

    def test_duplicate_created_by_a_concurrent_request_is_still_a_400(self):
        """The unique (parent, name_key) index backs up the pre-check."""
        batch = self.created("batch", "2027")
        self.created("department", "CSE", batch)
        with mock.patch("django.db.models.query.QuerySet.exists", return_value=False):
            self.assertFieldErrors(self.create("batch", " 2027"), "name")
            self.assertFieldErrors(self.create("department", "cse", batch), "name")
        self.assertEqual(Batch.objects.count(), 1)
        self.assertEqual(Department.objects.count(), 1)

    def test_level_must_be_known(self):
        for level in (None, "", "Batch", "school", "cohorts", 1, ["batch"], {"level": "batch"}):
            with self.subTest(level=level):
                response = self.api_post(STRUCTURE, {"level": level, "name": "X"}, user=self.admin)
                self.assertStatus(response, 400)
        self.assertStatus(self.api_post(STRUCTURE, {"name": "X"}, user=self.admin), 400)
        self.assertFalse(Batch.objects.exists())

    def test_parent_must_be_this_institutions_group_one_level_up(self):
        mine = make_chain(self.institution)
        theirs = make_chain(self.other)
        for index, level in enumerate(("department", "section", "cohort")):
            right_parent = mine[index]
            wrong_level = mine[index + 1] if index + 1 < 3 else mine[0]
            for bad in (None, "", "   ", "nope", 123, [str(right_parent.pk)], str(ObjectId()),
                        str(wrong_level.pk), str(theirs[index].pk)):
                with self.subTest(level=level, parentId=bad):
                    body = {"level": level, "name": "New"}
                    if bad is not None:
                        body["parentId"] = bad
                    self.assertFieldErrors(self.api_post(STRUCTURE, body, user=self.admin), "parentId")
        # ...and the other tenant can't use ours either.
        for index, level in enumerate(("department", "section", "cohort")):
            with self.subTest(level=level, as_user="other admin"):
                self.assertFieldErrors(self.create(level, "New", mine[index], as_user=self.other_admin), "parentId")
        for model in (Department, Section, Cohort):
            self.assertEqual(model.objects.count(), 2)

    def test_a_batch_ignores_any_parent(self):
        batch = self.created("batch", "2027", parent=str(make_batch(self.other).pk))
        self.assertEqual(batch.institution_id, self.institution.pk)

    def test_institution_in_the_body_is_ignored(self):
        response = self.api_post(
            STRUCTURE,
            {"level": "batch", "name": "2027", "institution": str(self.other.pk), "institutionId": str(self.other.pk)},
            user=self.admin,
        )
        self.assertStatus(response, 201)
        batch = Batch.objects.get(pk=response.json()["node"]["id"])
        self.assertEqual(batch.institution_id, self.institution.pk)
        self.assertEqual(self.tree(as_user=self.other_admin)["batches"], [])

    def test_children_take_the_parents_institution_not_the_body(self):
        batch = self.created("batch", "2027")
        response = self.api_post(
            STRUCTURE,
            {"level": "department", "name": "CSE", "parentId": str(batch.pk), "institutionId": str(self.other.pk)},
            user=self.admin,
        )
        self.assertStatus(response, 201)
        self.assertEqual(Department.objects.get().institution_id, self.institution.pk)

    def test_regex_metacharacters_are_literal(self):
        names = ["CSE 2027", "CSE.2027", "CSE (2027)", "CSE*", "CSE+", "CSE?", "CSE[1]", "C$E",
                 "^CSE", "CSE|ECE", "CSE\\2027", "CSE.*"]
        for name in names:
            with self.subTest(name=name):
                self.assertStatus(self.create("batch", name), 201)
        self.assertEqual(sorted(b["name"] for b in self.tree()["batches"]), sorted(names))
        for duplicate in ("cse.2027", "cse (2027)", "Cse.*"):
            with self.subTest(duplicate=duplicate):
                self.assertFieldErrors(self.create("batch", duplicate), "name")
        self.assertEqual(Batch.objects.count(), len(names))

    def test_name_is_required_and_at_most_60_characters(self):
        batch = make_batch(self.institution)
        for level, parent in (("batch", None), ("department", batch)):
            for bad in ("", "   ", None, 123, ["CSE"], "x" * 61, " ".join(["ab"] * 21)):
                with self.subTest(level=level, name=bad):
                    self.assertFieldErrors(self.create(level, bad, parent), "name")
            body = {"level": level, **({"parentId": str(parent.pk)} if parent else {})}
            self.assertFieldErrors(self.api_post(STRUCTURE, body, user=self.admin), "name")
        self.assertEqual(Batch.objects.count(), 1)
        self.assertFalse(Department.objects.exists())

        self.assertStatus(self.create("batch", "x" * 60), 201)
        # Length is measured after whitespace is collapsed.
        response = self.create("batch", "  " + "y" * 30 + "      " + "z" * 29 + "  ")
        self.assertStatus(response, 201)
        self.assertEqual(len(response.json()["node"]["name"]), 60)

    def test_same_name_may_exist_in_two_institutions(self):
        mine = self.create("batch", "2027")
        theirs = self.create("batch", "2027", as_user=self.other_admin)
        self.assertStatus(mine, 201)
        self.assertStatus(theirs, 201)
        self.assertEqual([b["id"] for b in self.tree()["batches"]], [mine.json()["node"]["id"]])
        self.assertEqual([b["id"] for b in self.tree(as_user=self.other_admin)["batches"]],
                         [theirs.json()["node"]["id"]])

    def test_malformed_body_is_400(self):
        for raw in ("{oops", "[]", "null"):
            with self.subTest(raw=raw):
                self.assertStatus(self.api_post(STRUCTURE, raw=raw, user=self.admin), 400)
        self.assertFalse(Batch.objects.exists())

    def test_new_cohort_can_take_students_right_away(self):
        batch = self.created("batch", "2027")
        section = self.created("section", "A", self.created("department", "CSE", batch))
        cohort_id = self.create("cohort", "Lab 1", section).json()["node"]["id"]
        response = self.api_post(
            USERS,
            {"name": "Ravi Kumar", "email": unique_email("ravi"), "role": "student",
             "password": PASSWORD, "cohortId": cohort_id},
            user=self.admin,
        )
        self.assertStatus(response, 201)
        user = response.json()["user"]
        self.assertEqual(user["cohort"]["id"], cohort_id)
        self.assertEqual(user["placement"]["label"], "2027 · CSE · A · Lab 1")
        self.assertEqual(user["placement"]["section"], {"id": str(section.pk), "name": "A"})
        self.assertEqual(self.tree()["batches"][0]["studentCount"], 1)

    def test_students_can_only_join_a_cohort(self):
        batch, department, section, _ = make_chain(self.institution)
        for node in (batch, department, section):
            with self.subTest(level=node.LEVEL):
                response = self.api_post(
                    USERS,
                    {"name": "Ravi Kumar", "email": unique_email("ravi"), "role": "student",
                     "password": PASSWORD, "cohortId": str(node.pk)},
                    user=self.admin,
                )
                self.assertFieldErrors(response, "cohortId")


class StructureTreeTests(StructureTestCase):
    def test_tree_nests_every_level_with_stats_and_is_tenant_scoped(self):
        b27, cse, a, lab1 = make_chain(self.institution, "2027", "CSE", "A", "Lab 1")
        lab2 = make_cohort(self.institution, "lab 2", section=a)
        b = make_section(cse, "B")
        ece = make_department(b27, "ECE")
        b26 = make_batch(self.institution, "2026")
        for _ in range(2):
            make_user(self.institution, "student", cohort=lab1)
        signed_in = make_user(self.institution, "student", cohort=lab2, last_login=timezone.now())
        PracticeAttempt.objects.create(
            institution=self.institution, user=signed_in, kind="mcq", subject="Java", subject_key="java", score=70,
        )
        make_user(self.other, "student", cohort=make_chain(self.other, "2027", "CSE", "A", "Lab 1")[3])

        def shape(nodes):
            return [
                {
                    "name": n["name"],
                    "students": n["studentCount"],
                    **({"children": shape(n["children"])} if "children" in n else {}),
                }
                for n in nodes
            ]

        expected = [
            {"name": "2026", "students": 0, "children": []},
            {"name": "2027", "students": 3, "children": [
                {"name": "CSE", "students": 3, "children": [
                    {"name": "A", "students": 3, "children": [
                        {"name": "Lab 1", "students": 2},
                        {"name": "lab 2", "students": 1},
                    ]},
                    {"name": "B", "students": 0, "children": []},
                ]},
                {"name": "ECE", "students": 0, "children": []},
            ]},
        ]
        for user in (self.admin, self.educator):
            with self.subTest(role=user.role):
                tree = self.tree(as_user=user)
                self.assertEqual(shape(tree["batches"]), expected)
                self.assertEqual(tree["counts"], {"batches": 2, "departments": 2, "sections": 2, "cohorts": 2})

        tree = self.tree()
        batch = tree["batches"][1]
        self.assertEqual((batch["id"], batch["activated"], batch["attempts"], batch["averageScore"]),
                         (str(b27.pk), 1, 1, 70.0))
        lab = batch["children"][0]["children"][0]["children"][1]
        self.assertEqual((lab["id"], lab["label"], lab["activated"], lab["attempts"]),
                         (str(lab2.pk), "2027 · CSE · A · lab 2", 1, 1))
        self.assertEqual(lab["path"][-2], {"level": "section", "id": str(a.pk), "name": "A"})
        self.assertEqual(
            [tree["batches"][0]["id"], batch["children"][1]["id"], batch["children"][0]["children"][1]["id"]],
            [str(b26.pk), str(ece.pk), str(b.pk)],
        )

        theirs = self.tree(as_user=self.other_admin)
        self.assertEqual(shape(theirs["batches"]), [
            {"name": "2027", "students": 1, "children": [{"name": "CSE", "students": 1, "children": [
                {"name": "A", "students": 1, "children": [{"name": "Lab 1", "students": 1}]}]}]},
        ])

    def test_tree_is_sorted_case_insensitively(self):
        for name in ("beta", "Alpha", "gamma", "Delta"):
            self.assertStatus(self.create("batch", name), 201)
        self.assertEqual([b["name"] for b in self.tree()["batches"]], ["Alpha", "beta", "Delta", "gamma"])


class GroupDetailTests(StructureTestCase):
    def setUp(self):
        super().setUp()
        self.batch, self.department, self.section, self.cohort = make_chain(
            self.institution, "2027", "CSE", "A", "Lab 1"
        )
        self.nodes = (self.batch, self.department, self.section, self.cohort)
        self.theirs = make_chain(self.other, "2027", "CSE", "A", "Lab 1")

    def test_get_returns_the_node_and_its_children(self):
        make_user(self.institution, "student", cohort=self.cohort)
        for user in (self.admin, self.educator):
            for index, node in enumerate(self.nodes):
                with self.subTest(role=user.role, level=node.LEVEL):
                    response = self.api_get(node_url(node), user=user)
                    self.assertStatus(response, 200)
                    entry = response.json()["node"]
                    self.assertEqual((entry["id"], entry["level"], entry["studentCount"]),
                                     (str(node.pk), node.LEVEL, 1))
                    self.assertEqual(entry["label"], " · ".join(["2027", "CSE", "A", "Lab 1"][: index + 1]))
                    if node.LEVEL == "cohort":
                        self.assertNotIn("children", entry)
                    else:
                        child = self.nodes[index + 1]
                        self.assertEqual([c["id"] for c in entry["children"]], [str(child.pk)])
                        self.assertEqual(entry["children"][0]["studentCount"], 1)

    def test_other_tenants_and_bad_ids_are_404(self):
        for node in self.theirs:
            with self.subTest(level=node.LEVEL):
                url = node_url(node)
                self.assertStatus(self.api_get(url, user=self.admin), 404)
                self.assertStatus(self.api_patch(url, {"name": "Mine now"}, user=self.admin), 404)
                self.assertStatus(self.api_delete(url, user=self.admin), 404)
                node.refresh_from_db()
                self.assertNotEqual(node.name, "Mine now")
        for url in (f"{STRUCTURE}/batch/nope", f"{STRUCTURE}/batch/{ObjectId()}",
                    f"{STRUCTURE}/section/{self.cohort.pk}",  # right id, wrong level
                    f"{STRUCTURE}/class/{self.cohort.pk}"):
            with self.subTest(url=url):
                self.assertStatus(self.api_get(url, user=self.admin), 404)
                self.assertStatus(self.api_delete(url, user=self.admin), 404)
        self.assertEqual(Cohort.objects.count(), 2)

    def test_rename(self):
        student = make_user(self.institution, "student", cohort=self.cohort)
        for node, name in zip(self.nodes, ("2023-2027", "Computer Science", "Morning", "Lab One")):
            with self.subTest(level=node.LEVEL):
                response = self.api_patch(node_url(node), {"name": f"  {name} "}, user=self.admin)
                self.assertStatus(response, 200)
                self.assertEqual(response.json()["node"]["name"], name)
                node.refresh_from_db()
                self.assertEqual((node.name, node.name_key), (name, name.casefold()))
        self.assertEqual(
            self.api_get(ME, user=student).json()["user"]["placement"]["label"],
            "2023-2027 · Computer Science · Morning · Lab One",
        )
        self.assertTrue(AuditLog.objects.filter(action="cohort.renamed").exists())

    def test_rename_rejects_a_sibling_name_but_not_a_cousins(self):
        ece = make_department(self.batch, "ECE")
        b = make_section(self.department, "B")
        make_section(ece, "C")
        for node, taken in ((ece, "cse"), (b, " a "), (make_batch(self.institution, "2028"), "2027")):
            with self.subTest(level=node.LEVEL):
                self.assertFieldErrors(self.api_patch(node_url(node), {"name": taken}, user=self.admin), "name")
        # "C" exists under ECE only, so section B (under CSE) may take it.
        self.assertStatus(self.api_patch(node_url(b), {"name": "c"}, user=self.admin), 200)
        # Changing only the case of a node's own name is allowed.
        response = self.api_patch(node_url(self.department), {"name": "cse"}, user=self.admin)
        self.assertStatus(response, 200)
        self.assertEqual(response.json()["node"]["name"], "cse")

    def test_rename_validates_the_name(self):
        for bad in ("", "  ", None, 5, "x" * 61):
            with self.subTest(name=bad):
                self.assertFieldErrors(self.api_patch(node_url(self.section), {"name": bad}, user=self.admin), "name")
        self.section.refresh_from_db()
        self.assertEqual(self.section.name, "A")

    def test_delete_an_empty_group(self):
        for node in reversed(self.nodes):
            with self.subTest(level=node.LEVEL):
                self.assertStatus(self.api_delete(node_url(node), user=self.admin), 204)
                self.assertFalse(type(node).objects.filter(pk=node.pk).exists())
        self.assertEqual(AuditLog.objects.filter(action__endswith=".deleted").count(), 4)
        self.assertEqual(Cohort.objects.count(), 1)  # the other tenant's

    def test_delete_refuses_groups_with_children(self):
        for node in self.nodes[:3]:
            with self.subTest(level=node.LEVEL):
                response = self.api_delete(node_url(node), user=self.admin)
                self.assertStatus(response, 400)
                self.assertIn("first", response.json()["message"])
                self.assertTrue(type(node).objects.filter(pk=node.pk).exists())

    def test_delete_refuses_groups_with_students(self):
        student = make_user(self.institution, "student", cohort=self.cohort)
        response = self.api_delete(node_url(self.cohort), user=self.admin)
        self.assertStatus(response, 400)
        self.assertIn("students", response.json()["message"])
        self.assertTrue(Cohort.objects.filter(pk=self.cohort.pk).exists())

        # Once the student moves away, it can go.
        elsewhere = make_cohort(self.institution, section=self.section)
        self.assertStatus(
            self.api_patch(f"{USERS}/{student.pk}", {"cohortId": str(elsewhere.pk)}, user=self.admin), 200
        )
        self.assertStatus(self.api_delete(node_url(self.cohort), user=self.admin), 204)

    def test_delete_refuses_groups_with_tests(self):
        empty_section = make_section(self.department, "Empty")
        test = make_test(self.institution, empty_section)
        response = self.api_delete(node_url(empty_section), user=self.admin)
        self.assertStatus(response, 400)
        self.assertIn("tests", response.json()["message"])
        test.delete()
        self.assertStatus(self.api_delete(node_url(empty_section), user=self.admin), 204)


class MoveStudentTests(StructureTestCase):
    def setUp(self):
        super().setUp()
        self.here = make_chain(self.institution, "2027", "CSE", "A", "Lab 1")
        self.there = make_chain(self.institution, "2028", "ECE", "B", "Lab 2")
        self.student = make_user(self.institution, "student", cohort=self.here[3])

    def move(self, user, cohort_id, as_user=None):
        return self.api_patch(f"{USERS}/{user.pk}", {"cohortId": cohort_id}, user=as_user or self.admin)

    def test_moving_sets_every_level(self):
        response = self.move(self.student, str(self.there[3].pk))
        self.assertStatus(response, 200)
        placement = response.json()["user"]["placement"]
        self.assertEqual(placement["label"], "2028 · ECE · B · Lab 2")
        self.assertEqual(placement["department"], {"id": str(self.there[1].pk), "name": "ECE"})
        self.student.refresh_from_db()
        self.assertEqual(
            (self.student.batch_id, self.student.department_id, self.student.section_id, self.student.cohort_id),
            tuple(n.pk for n in self.there),
        )
        log = AuditLog.objects.get(action="user.moved")
        self.assertEqual(log.metadata["fromLabel"], "2027 · CSE · A · Lab 1")
        self.assertIn("2028 · ECE · B · Lab 2", log.summary)

        # Moving to the cohort they're already in changes nothing.
        self.assertStatus(self.move(self.student, str(self.there[3].pk)), 200)
        self.assertEqual(AuditLog.objects.filter(action="user.moved").count(), 1)

    def test_only_students_can_be_moved(self):
        for user in (self.educator, self.admin):
            with self.subTest(role=user.role):
                self.assertStatus(self.move(user, str(self.there[3].pk)), 400)
                user.refresh_from_db()
                self.assertIsNone(user.cohort_id)

    def test_target_must_be_one_of_our_cohorts(self):
        theirs = make_chain(self.other)
        bad = [None, "", "nope", 5, [str(self.there[3].pk)], str(ObjectId()), str(self.there[2].pk),
               str(theirs[3].pk)]
        for cohort_id in bad:
            with self.subTest(cohortId=cohort_id):
                self.assertFieldErrors(self.move(self.student, cohort_id), "cohortId")
        self.assertFieldErrors(self.api_patch(f"{USERS}/{self.student.pk}", {}, user=self.admin), "cohortId")
        self.student.refresh_from_db()
        self.assertEqual(self.student.cohort_id, self.here[3].pk)

    def test_tenant_isolation_and_permissions(self):
        stranger = make_user(self.other, "student", cohort=make_chain(self.other)[3])
        self.assertStatus(self.move(stranger, str(self.there[3].pk)), 404)
        self.assertStatus(self.move(self.student, str(self.there[3].pk), as_user=self.other_admin), 404)
        self.assertStatus(self.api_patch(f"{USERS}/not-an-id", {"cohortId": str(self.there[3].pk)},
                                         user=self.admin), 404)
        for user in (self.educator, self.student):
            with self.subTest(role=user.role):
                self.assertStatus(self.move(self.student, str(self.there[3].pk), as_user=user), 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.cohort_id, self.here[3].pk)


# --------------------------------------------------------------------------- #
# Admin overview                                                               #
# --------------------------------------------------------------------------- #


class AdminOverviewTests(StructureTestCase):
    def test_counts_and_departments(self):
        b27, cse, a, lab1 = make_chain(self.institution, "2027", "CSE", "A", "Lab 1")
        ece = make_department(b27, "ECE")
        for _ in range(2):
            make_user(self.institution, "student", cohort=lab1, last_login=timezone.now())
        make_user(self.institution, "student", cohort=make_cohort(self.institution, section=make_section(ece)))
        make_chain(self.other)

        response = self.api_get(OVERVIEW, user=self.admin)
        self.assertStatus(response, 200)
        body = response.json()
        self.assertEqual(
            body["counts"],
            {"students": 3, "educators": 1, "admins": 1, "batches": 1, "departments": 2, "sections": 2,
             "cohorts": 2},
        )
        self.assertNotIn("cohorts", body)
        self.assertEqual(
            body["departments"],
            [
                {"id": str(cse.pk), "name": "CSE", "label": "2027 · CSE", "students": 2, "activated": 2,
                 "averageScore": None},
                {"id": str(ece.pk), "name": "ECE", "label": "2027 · ECE", "students": 1, "activated": 0,
                 "averageScore": None},
            ],
        )
        self.assertStatus(self.api_get(OVERVIEW, user=self.educator), 403)


# --------------------------------------------------------------------------- #
# CSV import                                                                   #
# --------------------------------------------------------------------------- #


class ImportUsersTests(StructureTestCase):
    HEADER = "name,email,role,password,batch,department,section,cohort\n"

    def upload(self, rows, commit=False, create_groups=False, as_user=None):
        data = {"file": SimpleUploadedFile("people.csv", (self.HEADER + rows).encode(), content_type="text/csv")}
        if commit:
            data["commit"] = "true"
        if create_groups:
            data["createGroups"] = "true"
        token = create_token(as_user or self.admin)
        return self.client.post(IMPORT, data, HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_existing_path_is_used(self):
        chain = make_chain(self.institution, "2027", "CSE", "A", "Lab 1")
        email = unique_email("ravi")
        rows = f"Ravi Kumar,{email},student,,2027, cse ,a,LAB 1\nTara Teacher,{unique_email('t')},educator,,,,,\n"
        preview = self.upload(rows)
        self.assertStatus(preview, 200)
        body = preview.json()
        self.assertEqual(body["summary"], {"total": 2, "valid": 2, "invalid": 0})
        self.assertEqual((body["missingGroups"], body["newGroups"]), ([], []))
        self.assertEqual(body["rows"][0]["placement"], "2027 · cse · a · LAB 1")
        self.assertEqual(body["rows"][1]["placement"], "")
        self.assertNotIn("cohort", body["rows"][0])
        self.assertFalse(User.objects.filter(email=email).exists())

        response = self.upload(rows, commit=True)
        self.assertStatus(response, 201)
        self.assertEqual((response.json()["created"], response.json()["groupsCreated"]), (2, []))
        student = User.objects.get(email=email)
        self.assertEqual(
            (student.batch_id, student.department_id, student.section_id, student.cohort_id),
            tuple(n.pk for n in chain),
        )
        self.assertIsNone(User.objects.get(role="educator", institution=self.institution,
                                           name="Tara Teacher").cohort_id)

    def test_students_need_all_four_levels(self):
        make_chain(self.institution, "2027", "CSE", "A", "Lab 1")
        rows = f"Ravi Kumar,{unique_email('r')},student,,2027,CSE,,Lab 1\n"
        row = self.upload(rows).json()["rows"][0]
        self.assertEqual(row["errors"], ["Students need a section"])

    def test_missing_groups_are_reported_stopping_at_the_first_missing_level(self):
        make_chain(self.institution, "2027", "CSE", "A", "Lab 1")
        rows = (
            f"Ravi Kumar,{unique_email('r')},student,,2027,ECE,A,Lab 1\n"
            f"Meera Nair,{unique_email('m')},student,,2027,CSE,B,Lab 1\n"
            f"John Doe,{unique_email('j')},student,,2027,ECE,X,Y\n"
        )
        body = self.upload(rows).json()
        self.assertEqual(body["rows"][0]["errors"], ['Department "2027 · ECE" doesn\'t exist'])
        self.assertEqual(body["rows"][1]["errors"], ['Section "2027 · CSE · B" doesn\'t exist'])
        self.assertEqual(body["rows"][2]["errors"], ['Department "2027 · ECE" doesn\'t exist'])
        self.assertEqual(
            body["missingGroups"],
            [{"level": "department", "label": "2027 · ECE"}, {"level": "section", "label": "2027 · CSE · B"}],
        )
        self.assertEqual(body["newGroups"], [])
        self.assertEqual(body["summary"]["valid"], 0)
        self.assertStatus(self.upload(rows, commit=True), 400)
        self.assertEqual(Department.objects.count(), 1)

    def test_create_groups_builds_the_whole_missing_path(self):
        b27, cse, _, _ = make_chain(self.institution, "2027", "CSE", "A", "Lab 1")
        make_chain(self.other, "2028", "ME", "C", "Lab 9")  # same names elsewhere don't count
        emails = [unique_email(n) for n in ("ravi", "meera", "john", "bad")]
        rows = (
            f"Ravi Kumar,{emails[0]},student,,2028,ME,C,Lab 9\n"   # all four levels are new
            f"Meera Nair,{emails[1]},student,,2028,me,c,lab 9\n"   # same new path, other case
            f"John Doe,{emails[2]},student,,2027,CSE,B,Lab 1\n"    # new section + cohort under CSE
            f"X,{emails[3]},student,,2029,Civil,A,Lab 1\n"         # invalid row: its groups aren't made
        )
        preview = self.upload(rows, create_groups=True)
        self.assertStatus(preview, 200)
        body = preview.json()
        self.assertEqual(body["missingGroups"], [])
        self.assertEqual(
            body["newGroups"],
            [
                {"level": "batch", "label": "2028"},
                {"level": "batch", "label": "2029"},
                {"level": "department", "label": "2028 · ME"},
                {"level": "department", "label": "2029 · Civil"},
                {"level": "section", "label": "2027 · CSE · B"},
                {"level": "section", "label": "2028 · ME · C"},
                {"level": "section", "label": "2029 · Civil · A"},
                {"level": "cohort", "label": "2027 · CSE · B · Lab 1"},
                {"level": "cohort", "label": "2028 · ME · C · Lab 9"},
                {"level": "cohort", "label": "2029 · Civil · A · Lab 1"},
            ],
        )
        self.assertEqual(Batch.objects.filter(institution=self.institution).count(), 1)  # preview only

        response = self.upload(rows, commit=True, create_groups=True)
        self.assertStatus(response, 201)
        body = response.json()
        self.assertEqual((body["created"], body["skipped"]), (3, 1))
        self.assertEqual(
            body["groupsCreated"],
            [
                {"level": "batch", "label": "2028"},
                {"level": "department", "label": "2028 · ME"},
                {"level": "section", "label": "2027 · CSE · B"},
                {"level": "section", "label": "2028 · ME · C"},
                {"level": "cohort", "label": "2027 · CSE · B · Lab 1"},
                {"level": "cohort", "label": "2028 · ME · C · Lab 9"},
            ],
        )
        self.assertNotIn("cohortsCreated", body)
        self.assertFalse(Batch.objects.filter(institution=self.institution, name="2029").exists())

        ravi, meera, john = (User.objects.get(email=e) for e in emails[:3])
        self.assertEqual(ravi.cohort_id, meera.cohort_id)
        lab9 = Cohort.objects.select_related("section__department__batch").get(pk=ravi.cohort_id)
        self.assertEqual(lab9.institution_id, self.institution.pk)
        self.assertEqual(lab9.label, "2028 · ME · C · Lab 9")
        self.assertEqual(
            (ravi.batch_id, ravi.department_id, ravi.section_id),
            (lab9.section.department.batch_id, lab9.section.department_id, lab9.section_id),
        )
        for node in lab9.lineage():
            self.assertEqual(node.institution_id, self.institution.pk)
        self.assertEqual((john.batch_id, john.department_id), (b27.pk, cse.pk))
        self.assertEqual(john.section.name, "B")
        self.assertEqual(john.section.department_id, cse.pk)
        self.assertEqual(Section.objects.filter(department=cse).count(), 2)

    def test_create_groups_flag_name(self):
        """The old createCohorts flag no longer creates anything."""
        rows = f"Ravi Kumar,{unique_email('r')},student,,2030,CSE,A,Lab 1\n"
        data = {"file": SimpleUploadedFile("p.csv", (self.HEADER + rows).encode()), "commit": "true",
                "createCohorts": "true"}
        response = self.client.post(IMPORT, data, HTTP_AUTHORIZATION=f"Bearer {create_token(self.admin)}")
        self.assertStatus(response, 400)
        self.assertFalse(Batch.objects.exists())

    def test_only_admins_can_import(self):
        rows = f"Ravi Kumar,{unique_email('r')},student,,2030,CSE,A,Lab 1\n"
        self.assertStatus(self.upload(rows, commit=True, create_groups=True, as_user=self.educator), 403)
        self.assertFalse(Batch.objects.exists())
