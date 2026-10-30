"""Tests for the users CSV export (GET /api/institution/users/export) and the
"update" mode of the users CSV import, including an export -> import round trip.
"""
import csv
import io

import bcrypt
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.auth import create_token
from accounts.models import LoginAttempt, User
from accounts.tests import (
    PASSWORD,
    ApiTestCase,
    make_batch,
    make_cohort,
    make_department,
    make_institution,
    make_section,
    make_user,
    unique_email,
)
from accounts.throttle import throttle_key
from institutions.models import AuditLog, Batch, Cohort, Department, Section
from institutions.tests import make_chain

IMPORT = "/api/institution/users/import"
EXPORT = "/api/institution/users/export"
HEADER = "name,email,role,password,batch,department,section,cohort"
COLUMNS = HEADER.split(",")
NEW_PASSWORD = "NewPass123"


class UserSheetTestCase(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        # 2027 > CSE > A > {Lab 1, Lab 2};  2027 > CSE > B > Lab 1;  2027 > ECE > A > Lab 1;  2028 > CSE > A > Lab 1
        self.b27, self.cse, self.sec_a, self.lab1 = make_chain(self.institution, "2027", "CSE", "A", "Lab 1")
        self.lab2 = make_cohort(self.institution, "Lab 2", section=self.sec_a)
        self.sec_b = make_section(self.cse, "B")
        self.b_lab1 = make_cohort(self.institution, "Lab 1", section=self.sec_b)
        self.ece = make_department(self.b27, "ECE")
        self.ece_lab1 = make_cohort(self.institution, "Lab 1", section=make_section(self.ece, "A"))
        _, _, _, self.b28_lab1 = make_chain(self.institution, "2028", "CSE", "A", "Lab 1")

        self.admin = make_user(self.institution, "admin", name="Asha Admin", email=unique_email("admin"))
        self.educator = make_user(self.institution, "educator", name="Esha Educator", email=unique_email("edu"))
        self.student = make_user(self.institution, "student", name="Ravi Kumar", email=unique_email("ravi"),
                                 cohort=self.lab1)
        self.student2 = make_user(self.institution, "student", name="Meera Nair", email=unique_email("meera"),
                                  cohort=self.lab2)

        self.other = make_institution()
        self.other_lab = make_chain(self.other, "2027", "CSE", "A", "Lab 1")[3]
        self.other_admin = make_user(self.other, "admin", name="Otto Admin")
        self.outsider = make_user(self.other, "student", name="Out Sider", email=unique_email("out"),
                                  cohort=self.other_lab)

    # --- helpers --------------------------------------------------------- #

    def auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {create_token(user)}"}

    def export(self, params=None, as_user=None):
        return self.client.get(EXPORT, params or {}, **self.auth(as_user or self.admin))

    def parse(self, response):
        """(header, [dict per row]) of an export response."""
        text = response.content.decode("utf-8")
        self.assertTrue(text.startswith("﻿"))
        rows = list(csv.reader(io.StringIO(text[1:], newline="")))
        return rows[0], [dict(zip(rows[0], r)) for r in rows[1:]]

    def emails(self, response):
        return [r["email"] for r in self.parse(response)[1]]

    def upload(self, rows=None, *, raw=None, mode="update", commit=False, create_groups=False, as_user=None):
        content = raw if raw is not None else (HEADER + "\n" + rows).encode()
        data = {"file": SimpleUploadedFile("people.csv", content, content_type="text/csv")}
        if mode is not None:
            data["mode"] = mode
        if commit:
            data["commit"] = "true"
        if create_groups:
            data["createGroups"] = "true"
        return self.client.post(IMPORT, data, **self.auth(as_user or self.admin))

    def line(self, user, *, name=None, email=None, role=None, password="", placement=None):
        """A CSV line for `user`, with any field overridden. placement: 4 names, or () for none."""
        if placement is None:
            placement = [getattr(user, f).name for f in User.PLACEMENT_FIELDS] if user.cohort_id else [""] * 4
        elif not placement:
            placement = [""] * 4
        cells = [name or user.name, email or user.email, role or user.role, password, *placement]
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerow(cells)
        return out.getvalue()

    def preview_row(self, rows, **kwargs):
        response = self.upload(rows, **kwargs)
        self.assertStatus(response, 200)
        return response.json()["rows"][0]

    def snapshot(self, user):
        user = User.objects.get(pk=user.pk)
        return (user.name, user.role, user.password, user.must_change_password, user.token_version,
                user.batch_id, user.department_id, user.section_id, user.cohort_id)


# --------------------------------------------------------------------------- #
# Export                                                                       #
# --------------------------------------------------------------------------- #


class ExportUsersTests(UserSheetTestCase):
    def test_only_admins_can_export(self):
        self.assertStatus(self.client.get(EXPORT), 401)
        self.assertStatus(self.export(as_user=self.educator), 403)
        self.assertStatus(self.export(as_user=self.student), 403)
        self.assertStatus(self.export(), 200)

    def test_only_get_is_allowed(self):
        self.assertStatus(self.client.post(EXPORT, {}, **self.auth(self.admin)), 405)

    def test_header_and_one_row_per_member_of_own_institution(self):
        response = self.export()
        self.assertStatus(response, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        header, rows = self.parse(response)
        self.assertEqual(header, COLUMNS)
        # Sorted by role, then name.
        self.assertEqual(
            [r["email"] for r in rows],
            [self.admin.email, self.educator.email, self.student2.email, self.student.email],
        )
        self.assertNotIn(self.outsider.email, response.content.decode())
        self.assertNotIn(self.other_admin.email, response.content.decode())
        by_email = {r["email"]: r for r in rows}
        self.assertEqual(
            by_email[self.student.email],
            {"name": "Ravi Kumar", "email": self.student.email, "role": "student", "password": "",
             "batch": "2027", "department": "CSE", "section": "A", "cohort": "Lab 1"},
        )
        self.assertEqual(by_email[self.student2.email]["cohort"], "Lab 2")
        for staff in (self.admin, self.educator):
            row = by_email[staff.email]
            self.assertEqual(row["role"], staff.role)
            self.assertEqual([row[c] for c in ("batch", "department", "section", "cohort")], [""] * 4)
        self.assertTrue(all(r["password"] == "" for r in rows))
        self.assertNotIn("$2", response.content.decode())  # no hashes either

    def test_other_institution_sees_only_its_own(self):
        self.assertEqual(
            self.emails(self.export(as_user=self.other_admin)),
            [self.other_admin.email, self.outsider.email],
        )

    def test_download_headers(self):
        response = self.export()
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="users-{self.institution.slug}-{timezone.localdate().isoformat()}.csv"',
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn(b"\r\n", response.content)

    def test_role_filter(self):
        self.assertEqual(self.emails(self.export({"role": "admin"})), [self.admin.email])
        self.assertEqual(self.emails(self.export({"role": "educator"})), [self.educator.email])
        self.assertEqual(self.emails(self.export({"role": "student"})), [self.student2.email, self.student.email])
        response = self.export({"role": "superuser"})
        self.assertStatus(response, 400)
        self.assertEqual(response.json()["message"], "Unknown role filter")

    def test_group_filters(self):
        ece_student = make_user(self.institution, "student", name="Eve", cohort=self.ece_lab1)
        b_student = make_user(self.institution, "student", name="Bob", cohort=self.b_lab1)
        b28_student = make_user(self.institution, "student", name="Zed", cohort=self.b28_lab1)
        cases = [
            ("batch", self.b27, {self.student, self.student2, ece_student, b_student}),
            ("batch", self.b28_lab1.section.department.batch, {b28_student}),
            ("department", self.cse, {self.student, self.student2, b_student}),
            ("department", self.ece, {ece_student}),
            ("section", self.sec_a, {self.student, self.student2}),
            ("section", self.sec_b, {b_student}),
            ("cohort", self.lab1, {self.student}),
            ("cohort", self.lab2, {self.student2}),
        ]
        for level, node, expected in cases:
            with self.subTest(level=level, node=node.name):
                response = self.export({level: str(node.pk)})
                self.assertStatus(response, 200)
                self.assertEqual(set(self.emails(response)), {u.email for u in expected})
        # Levels combine with each other and with the role filter.
        self.assertEqual(
            self.emails(self.export({"department": str(self.cse.pk), "cohort": str(self.lab2.pk)})),
            [self.student2.email],
        )
        self.assertEqual(self.emails(self.export({"role": "admin", "batch": str(self.b27.pk)})), [])

    def test_unknown_group_is_400(self):
        other_batch = Batch.objects.get(institution=self.other)
        for level, value in [("batch", str(other_batch.pk)), ("cohort", str(self.other_lab.pk)),
                             ("section", "not-an-id"), ("department", "64b7f0c2a1b2c3d4e5f60718")]:
            with self.subTest(level=level, value=value):
                response = self.export({level: value})
                self.assertStatus(response, 400)
                self.assertEqual(response.json()["message"], f"Unknown {level}")

    def test_search_filter(self):
        self.assertEqual(self.emails(self.export({"q": "meera"})), [self.student2.email])
        self.assertEqual(self.emails(self.export({"q": self.educator.email.split("@")[0].upper()})),
                         [self.educator.email])
        self.assertEqual(self.emails(self.export({"q": "Out Sider"})), [])  # other tenant
        self.assertEqual(self.emails(self.export({"q": "nobody-matches"})), [])
        self.assertStatus(self.export({"q": "a\x00b"}), 400)

    def test_formula_like_names_are_escaped(self):
        names = ["=SUM(1)", "+x", "-x", "@x"]
        for name in names:
            make_user(self.institution, "educator", name=name)
        response = self.export({"role": "educator"})
        exported = {r["name"] for r in self.parse(response)[1]}
        self.assertEqual(exported, {"Esha Educator", *(f"'{n}" for n in names)})
        self.assertIn("'=SUM(1)", response.content.decode())


# --------------------------------------------------------------------------- #
# Round trip                                                                   #
# --------------------------------------------------------------------------- #


class RoundTripTests(UserSheetTestCase):
    def test_unchanged_export_imports_as_nothing_to_update(self):
        for name in ["=SUM(1)", "+x", "-x", "@x"]:
            make_user(self.institution, "educator", name=name)
        make_user(self.institution, "student", name="=cmd|' /C calc'!A0", cohort=self.lab1)
        before = {u.pk: self.snapshot(u) for u in User.objects.filter(institution=self.institution)}
        content = self.export().content

        preview = self.client.post(
            IMPORT, {"file": SimpleUploadedFile("users.csv", content), "mode": "update"}, **self.auth(self.admin)
        )
        self.assertStatus(preview, 200)
        body = preview.json()
        self.assertEqual(body["mode"], "update")
        self.assertEqual(body["summary"], {"total": len(before), "valid": len(before), "invalid": 0, "changing": 0})
        for row in body["rows"]:
            self.assertEqual((row["errors"], row["changes"]), ([], []), row)
        self.assertIn("=SUM(1)", [r["name"] for r in body["rows"]])

        commit = self.client.post(
            IMPORT, {"file": SimpleUploadedFile("users.csv", content), "mode": "update", "commit": "true"},
            **self.auth(self.admin),
        )
        self.assertStatus(commit, 400)
        self.assertIn("Nothing to update", commit.json()["message"])
        self.assertEqual({u.pk: self.snapshot(u) for u in User.objects.filter(institution=self.institution)}, before)
        self.assertFalse(AuditLog.objects.filter(action="users.updated").exists())

    def test_edited_export_applies_only_the_edits(self):
        _, rows = self.parse(self.export())
        for row in rows:
            if row["email"] == self.student.email:
                row["cohort"] = "Lab 2"
            if row["email"] == self.educator.email:
                row["name"] = "Esha Teacher"
        out = io.StringIO()
        writer = csv.DictWriter(out, COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        response = self.upload(raw=out.getvalue().encode(), commit=True)
        self.assertStatus(response, 200)
        body = response.json()
        self.assertEqual((body["updated"], body["unchanged"], body["skipped"]), (2, 2, 0))
        self.assertEqual(User.objects.get(pk=self.student.pk).cohort_id, self.lab2.pk)
        self.assertEqual(User.objects.get(pk=self.educator.pk).name, "Esha Teacher")


# --------------------------------------------------------------------------- #
# Update mode: preview and commit                                              #
# --------------------------------------------------------------------------- #


class UpdateModeTests(UserSheetTestCase):
    def test_unknown_mode_is_400(self):
        for mode in ("replace", "", "UPDATE"):
            with self.subTest(mode=mode):
                response = self.upload(self.line(self.student, name="Changed"), mode=mode, commit=True)
                self.assertStatus(response, 400)
                self.assertEqual(response.json()["message"], "mode must be add or update")
        self.assertEqual(User.objects.get(pk=self.student.pk).name, "Ravi Kumar")

    def test_only_admins(self):
        rows = self.line(self.student, name="Changed")
        self.assertStatus(self.upload(rows, commit=True, as_user=self.educator), 403)
        self.assertStatus(self.upload(rows, commit=True, as_user=self.student), 403)
        self.assertEqual(User.objects.get(pk=self.student.pk).name, "Ravi Kumar")

    def test_matched_by_email_case_insensitively_and_name_change(self):
        rows = self.line(self.student, name="  Ravi   K  ", email=f"  {self.student.email.upper()} ")
        before = self.snapshot(self.student)
        preview = self.upload(rows)
        self.assertStatus(preview, 200)
        body = preview.json()
        self.assertEqual(body["summary"], {"total": 1, "valid": 1, "invalid": 0, "changing": 1})
        row = body["rows"][0]
        self.assertEqual(row["email"], self.student.email)
        self.assertEqual(row["changes"], ["Name: Ravi Kumar → Ravi K"])
        self.assertNotIn("_user", row)
        self.assertEqual(self.snapshot(self.student), before)  # preview never writes

        response = self.upload(rows, commit=True)
        self.assertStatus(response, 200)
        body = response.json()
        self.assertEqual(
            {k: body[k] for k in ("mode", "updated", "unchanged", "skipped", "groupsCreated")},
            {"mode": "update", "updated": 1, "unchanged": 0, "skipped": 0, "groupsCreated": []},
        )
        self.assertEqual(body["rows"][0]["changes"], ["Name: Ravi Kumar → Ravi K"])
        user = User.objects.get(pk=self.student.pk)
        self.assertEqual(user.name, "Ravi K")
        # Name-only: same password, still signed in, placement kept.
        self.assertEqual((user.password, user.token_version, user.must_change_password, user.cohort_id),
                         (before[2], before[4], before[3], self.lab1.pk))

    def test_placement_change_at_each_level(self):
        b28 = self.b28_lab1.section.department.batch
        cases = [
            (["2027", "CSE", "A", "Lab 2"], "Cohort: Lab 1 → Lab 2", self.lab2),
            (["2027", "CSE", "B", "Lab 1"], "Section: A · Lab 1 → B · Lab 1", self.b_lab1),
            (["2027", "ECE", "A", "Lab 1"], "Department: CSE · A · Lab 1 → ECE · A · Lab 1", self.ece_lab1),
            (["2028", "CSE", "A", "Lab 1"], "Batch: 2027 · CSE · A · Lab 1 → 2028 · CSE · A · Lab 1", self.b28_lab1),
        ]
        for placement, change, cohort in cases:
            with self.subTest(change=change):
                self.student.place(self.lab1)
                self.student.save()
                version = User.objects.get(pk=self.student.pk).token_version
                rows = self.line(self.student, placement=placement)
                self.assertEqual(self.preview_row(rows)["changes"], [change])
                response = self.upload(rows, commit=True)
                self.assertStatus(response, 200)
                self.assertEqual(response.json()["updated"], 1)
                user = User.objects.get(pk=self.student.pk)
                self.assertEqual(
                    (user.batch_id, user.department_id, user.section_id, user.cohort_id),
                    tuple(n.pk for n in cohort.lineage()),
                )
                self.assertEqual(user.token_version, version)  # placement alone doesn't sign out
        self.assertEqual(User.objects.get(pk=self.student.pk).batch_id, b28.pk)

    def test_placement_spelling_differences_are_not_changes(self):
        rows = self.line(self.student, placement=[" 2027 ", "cse", "a", "LAB  1"])
        row = self.preview_row(rows)
        self.assertEqual((row["errors"], row["changes"]), ([], []))

    def test_student_to_staff_clears_placement_and_signs_out(self):
        before = self.snapshot(self.student)
        rows = self.line(self.student, role="educator", placement=["2027", "CSE", "A", "Lab 1"])
        row = self.preview_row(rows)
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["placement"], "")  # staff placement columns are ignored
        self.assertEqual(row["changes"], ["Role: Student → Educator", "Placement: 2027 · CSE · A · Lab 1 → none"])
        self.assertStatus(self.upload(rows, commit=True), 200)
        user = User.objects.get(pk=self.student.pk)
        self.assertEqual(user.role, "educator")
        self.assertEqual((user.batch_id, user.department_id, user.section_id, user.cohort_id), (None,) * 4)
        self.assertEqual(user.token_version, before[4] + 1)
        self.assertEqual(user.password, before[2])
        self.assertFalse(user.must_change_password)

    def test_staff_to_student_needs_a_full_placement(self):
        row = self.preview_row(self.line(self.educator, role="student"))
        self.assertEqual(row["errors"], ["Students need a batch, department, section, cohort"])
        self.assertEqual(row["changes"], [])
        row = self.preview_row(self.line(self.educator, role="student", placement=["2027", "CSE", "", "Lab 1"]))
        self.assertEqual(row["errors"], ["Students need a section"])

        version = self.snapshot(self.educator)[4]
        rows = self.line(self.educator, role="student", placement=["2027", "CSE", "A", "Lab 2"])
        self.assertEqual(self.preview_row(rows)["changes"],
                         ["Role: Educator → Student", "Placement: none → 2027 · CSE · A · Lab 2"])
        self.assertStatus(self.upload(rows, commit=True), 200)
        user = User.objects.get(pk=self.educator.pk)
        self.assertEqual((user.role, user.cohort_id, user.section_id, user.department_id, user.batch_id),
                         ("student", self.lab2.pk, self.sec_a.pk, self.cse.pk, self.b27.pk))
        self.assertEqual(user.token_version, version + 1)

    def test_admin_and_educator_role_swap(self):
        other_admin = make_user(self.institution, "admin", name="Second Admin")
        rows = self.line(other_admin, role="educator") + self.line(self.educator, role="admin")
        response = self.upload(rows, commit=True)
        self.assertStatus(response, 200)
        self.assertEqual([r["changes"] for r in response.json()["rows"]],
                         [["Role: Admin → Educator"], ["Role: Educator → Admin"]])
        self.assertEqual(User.objects.get(pk=other_admin.pk).role, "educator")
        self.assertEqual(User.objects.get(pk=self.educator.pk).role, "admin")

    def test_new_password_is_hashed_and_signs_out(self):
        key = throttle_key("login", self.student.email)
        LoginAttempt.objects.create(key=key)
        LoginAttempt.objects.create(key=throttle_key("login", self.student2.email))
        before = self.snapshot(self.student)
        rows = self.line(self.student, password=NEW_PASSWORD)
        row = self.preview_row(rows)
        self.assertEqual(row["changes"], ["New password (they'll be signed out)"])
        self.assertTrue(row["passwordProvided"])
        self.assertNotIn(NEW_PASSWORD, self.upload(rows).content.decode())
        self.assertEqual(self.snapshot(self.student), before)
        self.assertTrue(LoginAttempt.objects.filter(key=key).exists())

        response = self.upload(rows, commit=True)
        self.assertStatus(response, 200)
        self.assertNotIn(NEW_PASSWORD, response.content.decode())
        user = User.objects.get(pk=self.student.pk)
        self.assertTrue(user.password.startswith("$2"))
        self.assertTrue(bcrypt.checkpw(NEW_PASSWORD.encode(), user.password.encode()))
        self.assertTrue(user.must_change_password)
        self.assertEqual(user.token_version, before[4] + 1)
        self.assertFalse(LoginAttempt.objects.filter(key=key).exists())
        self.assertEqual(LoginAttempt.objects.count(), 1)  # others' throttles untouched
        # Old token no longer works; the new password does.
        self.assertStatus(self.client.get("/api/auth/me", **{"HTTP_AUTHORIZATION": f"Bearer {create_token(self.student)}"}), 401)
        self.assertStatus(self.api_login(self.student.email, NEW_PASSWORD), 200)

    def test_role_and_password_together_bump_token_version_once(self):
        version = self.snapshot(self.educator)[4]
        rows = self.line(self.educator, role="admin", password=NEW_PASSWORD)
        self.assertStatus(self.upload(rows, commit=True), 200)
        self.assertEqual(User.objects.get(pk=self.educator.pk).token_version, version + 1)

    def test_blank_password_keeps_the_old_one(self):
        rows = self.line(self.student, name="Ravi New")
        self.assertStatus(self.upload(rows, commit=True), 200)
        user = User.objects.get(pk=self.student.pk)
        self.assertTrue(bcrypt.checkpw(PASSWORD.encode(), user.password.encode()))
        self.assertFalse(user.must_change_password)

    def test_unknown_groups_are_flagged_unless_create_groups(self):
        rows = self.line(self.student, placement=["2027", "CSE", "C", "Lab 9"])
        body = self.upload(rows).json()
        self.assertEqual(body["rows"][0]["errors"], ['Section "2027 · CSE · C" doesn\'t exist'])
        self.assertEqual(body["missingGroups"], [{"level": "section", "label": "2027 · CSE · C"}])
        self.assertEqual(body["summary"]["changing"], 0)
        self.assertStatus(self.upload(rows, commit=True), 400)
        self.assertFalse(Section.objects.filter(name="C").exists())

        body = self.upload(rows, create_groups=True).json()
        self.assertEqual(body["rows"][0]["errors"], [])
        self.assertEqual(body["rows"][0]["changes"], ["Section: A · Lab 1 → C · Lab 9"])
        self.assertEqual(body["newGroups"], [{"level": "section", "label": "2027 · CSE · C"},
                                             {"level": "cohort", "label": "2027 · CSE · C · Lab 9"}])
        self.assertFalse(Section.objects.filter(name="C").exists())  # preview only

        response = self.upload(rows, commit=True, create_groups=True)
        self.assertStatus(response, 200)
        self.assertEqual(response.json()["groupsCreated"],
                         [{"level": "section", "label": "2027 · CSE · C"},
                          {"level": "cohort", "label": "2027 · CSE · C · Lab 9"}])
        cohort = Cohort.objects.get(institution=self.institution, name="Lab 9")
        self.assertEqual(cohort.section.department_id, self.cse.pk)
        self.assertEqual(User.objects.get(pk=self.student.pk).cohort_id, cohort.pk)
        log = AuditLog.objects.get(action="users.updated")
        self.assertIn("and created 2027 · CSE · C, 2027 · CSE · C · Lab 9", log.summary)

    def test_create_groups_for_a_whole_new_path(self):
        rows = self.line(self.educator, role="student", placement=["2030", "Civil", "A", "Lab 1"])
        response = self.upload(rows, commit=True, create_groups=True)
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json()["groupsCreated"]), 4)
        user = User.objects.select_related("cohort").get(pk=self.educator.pk)
        self.assertEqual(user.cohort.label, "2030 · Civil · A · Lab 1")
        self.assertFalse(Batch.objects.filter(institution=self.other, name="2030").exists())

    def test_mixed_rows_report_updated_unchanged_and_skipped(self):
        rows = (
            self.line(self.student, name="Ravi Changed")       # updated
            + self.line(self.student2)                         # unchanged
            + self.line(self.educator, role="wizard")          # skipped: bad role
            + f"Ghost,{unique_email('ghost')},student,,2027,CSE,A,Lab 1\n"  # skipped: not a member
        )
        preview = self.upload(rows).json()
        self.assertEqual(preview["summary"], {"total": 4, "valid": 2, "invalid": 2, "changing": 1})
        response = self.upload(rows, commit=True)
        self.assertStatus(response, 200)
        body = response.json()
        self.assertEqual((body["updated"], body["unchanged"], body["skipped"]), (1, 1, 2))
        self.assertEqual([r["line"] for r in body["rows"]], [2, 3, 4, 5])
        self.assertEqual([r["changes"] for r in body["rows"]], [["Name: Ravi Kumar → Ravi Changed"], [], [], []])
        self.assertEqual(body["rows"][2]["errors"], ["Role must be admin, educator or student"])
        self.assertEqual(body["rows"][3]["errors"], ["No user with this email in your institution"])
        self.assertEqual(User.objects.get(pk=self.student.pk).name, "Ravi Changed")
        self.assertEqual(User.objects.get(pk=self.educator.pk).role, "educator")
        self.assertNotIn("credentials", body)
        self.assertNotIn("created", body)


# --------------------------------------------------------------------------- #
# Update mode: errors                                                          #
# --------------------------------------------------------------------------- #


class UpdateModeErrorTests(UserSheetTestCase):
    def test_email_from_another_institution_is_not_revealed_or_modified(self):
        before = self.snapshot(self.outsider)
        unknown = unique_email("nobody")
        rows = (
            self.line(self.outsider, name="Hijacked", role="admin", password=NEW_PASSWORD, placement=())
            + f"Nobody Here,{unknown},educator,,,,,\n"
            + self.line(self.student, name="Ravi Valid")
        )
        body = self.upload(rows).json()
        self.assertEqual(body["rows"][0]["errors"], ["No user with this email in your institution"])
        self.assertEqual(body["rows"][1]["errors"], ["No user with this email in your institution"])
        self.assertEqual(body["rows"][0]["changes"], [])

        response = self.upload(rows, commit=True)
        self.assertStatus(response, 200)
        self.assertEqual((response.json()["updated"], response.json()["skipped"]), (1, 2))
        self.assertEqual(self.snapshot(self.outsider), before)
        self.assertEqual(User.objects.get(pk=self.outsider.pk).institution_id, self.other.pk)
        self.assertFalse(User.objects.filter(email=unknown).exists())  # update never creates

    def test_duplicate_email_in_the_file(self):
        rows = self.line(self.student, name="First") + self.line(self.student, email=self.student.email.upper(),
                                                                  name="Second")
        body = self.upload(rows).json()
        self.assertEqual(body["rows"][0]["errors"], [])
        self.assertEqual(body["rows"][1]["errors"], ["Same email as row 2"])
        self.assertEqual(body["rows"][1]["changes"], [])
        self.assertStatus(self.upload(rows, commit=True), 200)
        self.assertEqual(User.objects.get(pk=self.student.pk).name, "First")

    def test_admin_cannot_change_their_own_role_but_can_rename_themselves(self):
        for role in ("educator", "student"):
            with self.subTest(role=role):
                placement = ["2027", "CSE", "A", "Lab 1"] if role == "student" else ()
                row = self.preview_row(self.line(self.admin, role=role, placement=placement))
                self.assertIn("You can't change your own role", row["errors"])
                self.assertStatus(self.upload(self.line(self.admin, role=role, placement=placement),
                                              commit=True), 400)
        self.assertEqual(User.objects.get(pk=self.admin.pk).role, "admin")

        version = self.snapshot(self.admin)[4]
        rows = self.line(self.admin, name="Asha Principal")
        self.assertEqual(self.preview_row(rows)["changes"], ["Name: Asha Admin → Asha Principal"])
        self.assertStatus(self.upload(rows, commit=True), 200)
        me = User.objects.get(pk=self.admin.pk)
        self.assertEqual((me.name, me.role, me.token_version), ("Asha Principal", "admin", version))
        # Another admin may change someone else's admin role.
        second = make_user(self.institution, "admin")
        self.assertStatus(self.upload(self.line(self.admin, role="educator"), commit=True, as_user=second), 200)
        self.assertEqual(User.objects.get(pk=self.admin.pk).role, "educator")

    def test_invalid_values(self):
        cases = [
            (self.line(self.student, role="teacher"), "Role must be admin, educator or student"),
            (self.line(self.student, password="short"), "Password must be at least 6 characters"),
            (self.line(self.student, password="alllowercase1"),
             "Password must contain a lowercase letter, an uppercase letter and a number"),
            (self.line(self.student, name="X"), "Name must be 2-50 characters"),
            (f",{self.student.email},student,,2027,CSE,A,Lab 1\n", "Name is missing"),
            ("Ravi Kumar,not-an-email,student,,2027,CSE,A,Lab 1\n", "Email isn't valid"),
            ("Ravi Kumar,,student,,2027,CSE,A,Lab 1\n", "Email is missing"),
        ]
        before = self.snapshot(self.student)
        for rows, message in cases:
            with self.subTest(message=message):
                row = self.preview_row(rows)
                self.assertIn(message, row["errors"])
                self.assertEqual(row["changes"], [])
                response = self.upload(rows, commit=True)
                self.assertStatus(response, 400)
                self.assertIn("None of the rows can be imported", response.json()["message"])
        self.assertEqual(self.snapshot(self.student), before)
        self.assertFalse(AuditLog.objects.exists())

    def test_file_problems_are_400(self):
        response = self.upload(raw=b"name,email\nRavi,r@example.edu\n")
        self.assertStatus(response, 400)
        self.assertIn("Missing column", response.json()["message"])
        self.assertStatus(self.upload(raw=(HEADER + "\n").encode()), 400)


# --------------------------------------------------------------------------- #
# Audit log and add mode                                                       #
# --------------------------------------------------------------------------- #


class ImportAuditTests(UserSheetTestCase):
    def test_update_commit_is_logged_with_counts_and_preview_is_not(self):
        rows = (
            self.line(self.student, name="Ravi A") + self.line(self.student2, placement=["2027", "CSE", "A", "Lab 1"])
            + self.line(self.educator) + self.line(self.outsider)
        )
        self.assertStatus(self.upload(rows), 200)
        self.assertFalse(AuditLog.objects.exists())

        self.assertStatus(self.upload(rows, commit=True), 200)
        log = AuditLog.objects.get()
        self.assertEqual((log.action, log.institution_id, log.actor_id),
                         ("users.updated", self.institution.pk, self.admin.pk))
        self.assertEqual(log.summary, "Updated 2 users from a CSV file")
        self.assertEqual(log.metadata, {"updated": 2, "unchanged": 1, "skipped": 1})
        self.assertFalse(AuditLog.objects.filter(institution=self.other).exists())

    def test_single_update_summary_is_singular(self):
        self.assertStatus(self.upload(self.line(self.student, name="Ravi B"), commit=True), 200)
        self.assertEqual(AuditLog.objects.get().summary, "Updated 1 user from a CSV file")

    def test_add_mode_is_the_default_and_still_logs_imported(self):
        email = unique_email("new")
        rows = f"New Person,{email},educator,,,,,\n"
        preview = self.upload(rows, mode=None)
        self.assertStatus(preview, 200)
        self.assertEqual(preview.json()["mode"], "add")
        self.assertNotIn("changing", preview.json()["summary"])
        self.assertNotIn("changes", preview.json()["rows"][0])

        response = self.upload(rows, mode="add", commit=True)
        self.assertStatus(response, 201)
        self.assertEqual((response.json()["mode"], response.json()["created"]), ("add", 1))
        self.assertTrue(User.objects.filter(email=email, institution=self.institution).exists())
        self.assertEqual(AuditLog.objects.get().action, "users.imported")

    def test_add_mode_rejects_existing_members(self):
        body = self.upload(self.line(self.student, name="Dup"), mode="add").json()
        self.assertEqual(body["rows"][0]["errors"], ["An account with this email already exists"])


class RoundTripEdgeCaseTests(UserSheetTestCase):
    def test_names_already_starting_with_an_escaped_formula_survive(self):
        """A stored name like "'=x" must not lose its apostrophe on the way back."""
        for name in ["'=x", "'-Ann", "'+1"]:
            make_user(self.institution, "educator", name=name)
        content = self.export({"role": "educator"}).content
        response = self.client.post(
            IMPORT, {"file": SimpleUploadedFile("users.csv", content), "mode": "update"}, **self.auth(self.admin)
        )
        self.assertStatus(response, 200)
        self.assertEqual(response.json()["summary"]["changing"], 0, response.json()["rows"])
