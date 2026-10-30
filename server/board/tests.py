"""Tests for notes and messages (/api/board/).

Fixtures are built in setUp() (the MongoDB backend flushes between tests
rather than rolling back); see accounts/tests.py for the shared helpers.

The structure used throughout:

    batch b1 ── department d1 ── section s1 ── cohorts c1 (student st_c1), c2 (st_c2)
                              └─ section s2 ── cohort  c3 (st_c3)        sibling section
             └─ department d2 ── section s3 ── cohort  c4 (st_c4)        sibling department
    batch b2 ── ... ── cohort c5 (st_c5)                                 another batch
    an unplaced student, and a second institution with its own admin, group and student.
"""
from datetime import timedelta
from urllib.parse import quote

from bson import ObjectId
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.auth import create_token
from accounts.tests import (
    ApiTestCase,
    make_batch,
    make_cohort,
    make_department,
    make_institution,
    make_section,
    make_user,
)
from board.models import Attachment, Post, PostRead
from board.views import FILE_TYPES
from institutions.models import AuditLog

POSTS = "/api/board/posts"
UNREAD = "/api/board/unread"
USERS = "/api/institution/users"
STRUCTURE = "/api/institution/structure"
MB = 1024 * 1024


def post_url(post_id):
    return f"{POSTS}/{post_id}"


def read_url(post_id):
    return f"{POSTS}/{post_id}/read"


def attachments_url(post_id):
    return f"{POSTS}/{post_id}/attachments"


def attachment_url(post_id, attachment_id):
    return f"{POSTS}/{post_id}/attachments/{attachment_id}"


def upload(name="notes.pdf", content=b"%PDF-1.4 hello", content_type="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class BoardTestCase(ApiTestCase):
    def setUp(self):
        self.inst = make_institution()
        self.b1 = make_batch(self.inst, "2026")
        self.d1 = make_department(self.b1, "CSE")
        self.s1 = make_section(self.d1, "A")
        self.c1 = make_cohort(self.inst, "Lab 1", section=self.s1)
        self.c2 = make_cohort(self.inst, "Lab 2", section=self.s1)
        self.s2 = make_section(self.d1, "B")
        self.c3 = make_cohort(self.inst, "Lab 3", section=self.s2)
        self.d2 = make_department(self.b1, "ECE")
        self.s3 = make_section(self.d2, "A")
        self.c4 = make_cohort(self.inst, "Lab 4", section=self.s3)
        self.c5 = make_cohort(self.inst, "Lab 5")  # its own batch, department and section
        self.b2 = self.c5.section.department.batch

        self.admin = make_user(self.inst, "admin", name="Ada Admin")
        self.educator = make_user(self.inst, "educator", name="Ed Educator")
        self.other_educator = make_user(self.inst, "educator", name="Olly Educator")
        self.st_c1 = make_user(self.inst, "student", cohort=self.c1, name="Stu One")
        self.st_c2 = make_user(self.inst, "student", cohort=self.c2, name="Stu Two")
        self.st_c3 = make_user(self.inst, "student", cohort=self.c3, name="Stu Three")
        self.st_c4 = make_user(self.inst, "student", cohort=self.c4, name="Stu Four")
        self.st_c5 = make_user(self.inst, "student", cohort=self.c5, name="Stu Five")
        self.unplaced = make_user(self.inst, "student", name="Stu Nowhere")

        self.other_inst = make_institution()
        self.other_cohort = make_cohort(self.other_inst)
        self.other_batch = self.other_cohort.section.department.batch
        self.other_admin = make_user(self.other_inst, "admin")
        self.other_student = make_user(self.other_inst, "student", cohort=self.other_cohort)

    # --- helpers ---------------------------------------------------------- #

    def multipart(self, path, data, user):
        return self.client.post(path, data, HTTP_AUTHORIZATION=f"Bearer {create_token(user)}")

    def download(self, path, user):
        return self.client.get(path, HTTP_AUTHORIZATION=f"Bearer {create_token(user)}")

    def create(self, user=None, node=None, *, level=None, title="Hello", body="Some text", kind="message",
               files=None, pinned=False, **extra):
        user = user or self.educator
        node = node if node is not None else self.b1
        data = {"kind": kind, "title": title, "audienceLevel": level or node.LEVEL, "audienceId": str(node.pk)}
        if body is not None:
            data["body"] = body
        if pinned:
            data["pinned"] = "true"
        if files:
            data["files"] = files
        data.update(extra)
        return self.multipart(POSTS, data, user)

    def make_post(self, *args, **kwargs):
        response = self.create(*args, **kwargs)
        self.assertStatus(response, 201)
        return response.json()["post"]

    def ids(self, response):
        self.assertStatus(response, 200)
        return [p["id"] for p in response.json()["posts"]]

    def age(self, post_id, minutes):
        """Backdate a post so ordering doesn't depend on the clock's resolution."""
        Post.objects.filter(pk=post_id).update(created_at=timezone.now() - timedelta(minutes=minutes))


# --------------------------------------------------------------------------- #
# Access control                                                               #
# --------------------------------------------------------------------------- #


class AccessTests(BoardTestCase):
    def test_unauthenticated_requests_are_401(self):
        post = self.make_post(files=[upload()])
        attachment = post["attachments"][0]["id"]
        for method, path in [
            ("GET", POSTS),
            ("POST", POSTS),
            ("GET", UNREAD),
            ("GET", post_url(post["id"])),
            ("PATCH", post_url(post["id"])),
            ("DELETE", post_url(post["id"])),
            ("POST", read_url(post["id"])),
            ("POST", attachments_url(post["id"])),
            ("GET", attachment_url(post["id"], attachment)),
            ("DELETE", attachment_url(post["id"], attachment)),
        ]:
            with self.subTest(method=method, path=path):
                self.assertStatus(self.request(method, path), 401)
                self.assertStatus(self.request(method, path, token="not-a-token"), 401)

    def test_students_cannot_create(self):
        response = self.create(self.st_c1, self.c1)
        self.assertStatus(response, 403)
        self.assertFalse(Post.objects.exists())

    def test_student_cannot_change_a_visible_post(self):
        post = self.make_post(node=self.c1)
        self.assertStatus(self.api_patch(post_url(post["id"]), {"title": "Hacked"}, user=self.st_c1), 403)
        self.assertStatus(self.api_delete(post_url(post["id"]), user=self.st_c1), 403)
        self.assertEqual(Post.objects.get(pk=post["id"]).title, "Hello")

    def test_student_gets_404_changing_a_post_they_cannot_see(self):
        post = self.make_post(node=self.c1)
        self.assertStatus(self.api_patch(post_url(post["id"]), {"title": "Hacked"}, user=self.st_c3), 404)
        self.assertStatus(self.api_delete(post_url(post["id"]), user=self.st_c3), 404)
        self.assertTrue(Post.objects.filter(pk=post["id"]).exists())

    def test_students_cannot_add_or_delete_attachments(self):
        post = self.make_post(node=self.c1, files=[upload()])
        attachment = post["attachments"][0]["id"]
        response = self.multipart(attachments_url(post["id"]), {"files": [upload("x.pdf")]}, self.st_c1)
        self.assertStatus(response, 403)
        self.assertStatus(self.api_delete(attachment_url(post["id"], attachment), user=self.st_c1), 403)
        self.assertStatus(self.api_delete(attachment_url(post["id"], attachment), user=self.st_c3), 404)
        self.assertEqual(Attachment.objects.filter(post_id=post["id"]).count(), 1)

    def test_educator_manages_only_own_posts(self):
        mine = self.make_post(self.educator, title="Mine")
        theirs = self.make_post(self.other_educator, title="Theirs")
        self.assertStatus(self.api_patch(post_url(theirs["id"]), {"title": "X"}, user=self.educator), 403)
        self.assertStatus(self.api_delete(post_url(theirs["id"]), user=self.educator), 403)
        response = self.multipart(attachments_url(theirs["id"]), {"files": [upload()]}, self.educator)
        self.assertStatus(response, 403)
        # ...but may read it, and is told it can't edit it.
        response = self.api_get(post_url(theirs["id"]), user=self.educator)
        self.assertStatus(response, 200)
        self.assertIs(response.json()["post"]["canEdit"], False)

        response = self.api_patch(post_url(mine["id"]), {"title": "Mine, edited"}, user=self.educator)
        self.assertStatus(response, 200)
        self.assertIs(response.json()["post"]["canEdit"], True)
        self.assertStatus(self.api_delete(post_url(mine["id"]), user=self.educator), 204)
        self.assertFalse(Post.objects.filter(pk=mine["id"]).exists())

    def test_educator_cannot_delete_others_attachment(self):
        theirs = self.make_post(self.other_educator, files=[upload()])
        attachment = theirs["attachments"][0]["id"]
        self.assertStatus(self.api_delete(attachment_url(theirs["id"], attachment), user=self.educator), 403)
        # Downloading is fine for any staff member of the institution.
        self.assertStatus(self.download(attachment_url(theirs["id"], attachment), self.educator), 200)

    def test_admin_manages_every_post(self):
        post = self.make_post(self.educator, files=[upload()])
        response = self.api_get(post_url(post["id"]), user=self.admin)
        self.assertIs(response.json()["post"]["canEdit"], True)
        response = self.api_patch(post_url(post["id"]), {"title": "By admin", "pinned": True}, user=self.admin)
        self.assertStatus(response, 200)
        self.assertEqual(response.json()["post"]["title"], "By admin")
        response = self.multipart(attachments_url(post["id"]), {"files": [upload("more.txt", b"hi")]}, self.admin)
        self.assertStatus(response, 201)
        attachment = post["attachments"][0]["id"]
        self.assertStatus(self.api_delete(attachment_url(post["id"], attachment), user=self.admin), 204)
        self.assertStatus(self.api_delete(post_url(post["id"]), user=self.admin), 204)
        self.assertFalse(Post.objects.exists())

    def test_admin_can_post(self):
        post = self.make_post(self.admin, self.c1)
        self.assertEqual(post["author"]["id"], str(self.admin.pk))
        self.assertEqual(post["author"]["role"], "admin")

    def test_mark_read_is_student_only(self):
        post = self.make_post()
        for user in (self.admin, self.educator):
            with self.subTest(role=user.role):
                self.assertStatus(self.api_post(read_url(post["id"]), user=user), 403)
        self.assertFalse(PostRead.objects.exists())

    def test_other_tenant_staff_cannot_reach_posts(self):
        post = self.make_post(files=[upload()])
        attachment = post["attachments"][0]["id"]
        self.assertStatus(self.api_get(post_url(post["id"]), user=self.other_admin), 404)
        self.assertStatus(self.api_patch(post_url(post["id"]), {"title": "X"}, user=self.other_admin), 404)
        self.assertStatus(self.api_delete(post_url(post["id"]), user=self.other_admin), 404)
        self.assertStatus(self.download(attachment_url(post["id"], attachment), self.other_admin), 404)
        self.assertStatus(self.api_delete(attachment_url(post["id"], attachment), user=self.other_admin), 404)
        response = self.multipart(attachments_url(post["id"]), {"files": [upload()]}, self.other_admin)
        self.assertStatus(response, 404)
        self.assertEqual(self.ids(self.api_get(POSTS, user=self.other_admin)), [])
        self.assertEqual(Attachment.objects.count(), 1)

    def test_malformed_and_unknown_ids_are_404(self):
        post = self.make_post(files=[upload()])
        missing = str(ObjectId())
        for path in (post_url("nope"), post_url(missing), attachment_url("nope", "nope"),
                     attachment_url(post["id"], "nope"), attachment_url(post["id"], missing)):
            with self.subTest(path=path):
                self.assertStatus(self.api_get(path, user=self.admin), 404)
        self.assertStatus(self.api_post(read_url("nope"), user=self.st_c1), 404)

    def test_methods_not_allowed(self):
        self.assertStatus(self.api_put(POSTS, {}, user=self.admin), 405)
        self.assertStatus(self.api_get(read_url(str(ObjectId())), user=self.st_c1), 405)
        self.assertStatus(self.api_get(attachments_url(str(ObjectId())), user=self.admin), 405)


# --------------------------------------------------------------------------- #
# Creating posts                                                               #
# --------------------------------------------------------------------------- #


class CreateTests(BoardTestCase):
    def test_create_message(self):
        response = self.create(self.educator, self.s1, title="  Exam   on  Friday ", body="  Bring pencils.  ",
                               pinned=True)
        self.assertStatus(response, 201)
        body = response.json()
        self.assertIs(body["success"], True)
        post = body["post"]
        self.assertEqual(post["kind"], "message")
        self.assertEqual(post["title"], "Exam on Friday")
        self.assertEqual(post["body"], "Bring pencils.")
        self.assertIs(post["pinned"], True)
        self.assertIsNone(post["editedAt"])
        self.assertEqual(post["audience"]["level"], "section")
        self.assertEqual(post["audience"]["id"], str(self.s1.pk))
        self.assertEqual(post["audience"]["label"], "2026 · CSE · A")
        self.assertEqual([n["level"] for n in post["audience"]["path"]], ["batch", "department", "section"])
        self.assertEqual(post["author"], {"id": str(self.educator.pk), "name": "Ed Educator", "role": "educator"})
        self.assertIs(post["canEdit"], True)
        self.assertEqual(post["audienceSize"], 2)  # st_c1 and st_c2
        self.assertEqual(post["readers"], 0)
        self.assertNotIn("read", post)

        stored = Post.objects.get(pk=post["id"])
        self.assertEqual(stored.institution_id, self.inst.pk)
        self.assertEqual((stored.batch_id, stored.department_id, stored.section_id, stored.cohort_id),
                         (self.b1.pk, self.d1.pk, self.s1.pk, None))

    def test_pinned_defaults_to_false(self):
        self.assertIs(self.make_post()["pinned"], False)
        response = self.multipart(POSTS, {"title": "T", "body": "B", "pinned": "yes", "audienceLevel": "batch",
                                          "audienceId": str(self.b1.pk)}, self.educator)
        self.assertStatus(response, 201)
        self.assertIs(response.json()["post"]["pinned"], False)

    def test_audit_log_written(self):
        post = self.make_post(self.educator, self.c1, title="Lab rules", kind="note")
        log = AuditLog.objects.get(institution=self.inst, action="post.created")
        self.assertEqual(log.actor_id, self.educator.pk)
        self.assertEqual(log.metadata, {"postId": post["id"]})
        self.assertIn("Lab rules", log.summary)
        self.assertIn("note", log.summary)
        self.assertIn(self.c1.label, log.summary)

    def test_audience_at_every_level(self):
        for node in (self.b1, self.d1, self.s1, self.c1):
            with self.subTest(level=node.LEVEL):
                post = self.make_post(node=node)
                self.assertEqual(post["audience"]["level"], node.LEVEL)
                self.assertEqual(post["audience"]["id"], str(node.pk))

    def test_kind_is_validated(self):
        self.assertFieldErrors(self.create(kind="announcement"), "kind")
        self.assertFieldErrors(self.create(kind=""), "kind")
        # Omitted kind defaults to message.
        response = self.multipart(POSTS, {"title": "T", "body": "B", "audienceLevel": "batch",
                                          "audienceId": str(self.b1.pk)}, self.educator)
        self.assertStatus(response, 201)
        self.assertEqual(response.json()["post"]["kind"], "message")

    def test_title_is_required_and_limited(self):
        self.assertFieldErrors(self.create(title=""), "title")
        self.assertFieldErrors(self.create(title="   \t "), "title")
        self.assertFieldErrors(self.create(title="x" * 201), "title")
        response = self.multipart(POSTS, {"body": "B", "audienceLevel": "batch", "audienceId": str(self.b1.pk)},
                                  self.educator)
        self.assertFieldErrors(response, "title")
        self.assertEqual(len(self.make_post(title="x" * 200)["title"]), 200)

    def test_body_is_limited(self):
        self.assertFieldErrors(self.create(body="x" * 10_001), "body")
        self.assertEqual(len(self.make_post(body="x" * 10_000)["body"]), 10_000)

    def test_message_needs_text_or_a_file(self):
        self.assertFieldErrors(self.create(kind="message", body=None), "body")
        self.assertFieldErrors(self.create(kind="message", body="   "), "body")
        post = self.make_post(kind="message", body=None, files=[upload()])
        self.assertEqual(post["body"], "")
        self.assertEqual(len(post["attachments"]), 1)

    def test_note_may_be_title_only(self):
        post = self.make_post(kind="note", title="Reading week", body=None)
        self.assertEqual(post["kind"], "note")
        self.assertEqual(post["body"], "")
        self.assertEqual(post["attachments"], [])

    def test_audience_is_validated(self):
        cases = {
            "missing": {"audienceLevel": "", "audienceId": ""},
            "malformed id": {"audienceLevel": "batch", "audienceId": "not-an-id"},
            "unknown id": {"audienceLevel": "batch", "audienceId": str(ObjectId())},
            "unknown level": {"audienceLevel": "school", "audienceId": str(self.b1.pk)},
            "wrong level": {"audienceLevel": "section", "audienceId": str(self.b1.pk)},
            "other tenant": {"audienceLevel": "batch", "audienceId": str(self.other_batch.pk)},
            "other tenant cohort": {"audienceLevel": "cohort", "audienceId": str(self.other_cohort.pk)},
        }
        for label, audience in cases.items():
            with self.subTest(label):
                self.assertFieldErrors(self.create(**audience), "audience")
        response = self.multipart(POSTS, {"title": "T", "body": "B"}, self.educator)
        self.assertFieldErrors(response, "audience")
        self.assertFalse(Post.objects.exists())

    def test_several_errors_reported_together(self):
        response = self.create(kind="poll", title="", body="x" * 10_001, audienceId="bad")
        self.assertFieldErrors(response, "kind", "title", "body", "audience")

    def test_files_are_stored(self):
        pdf = b"%PDF-1.4 " + bytes(range(256))
        post = self.make_post(files=[upload("Syllabus.PDF", pdf), upload("notes.txt", b"hello", "text/plain")])
        self.assertEqual(
            [(a["name"], a["contentType"], a["size"]) for a in post["attachments"]],
            [("Syllabus.PDF", "application/pdf", len(pdf)), ("notes.txt", "text/plain", 5)],
        )
        stored = Attachment.objects.get(post_id=post["id"], name="Syllabus.PDF")
        self.assertEqual(bytes(stored.data), pdf)

    def test_content_type_comes_from_the_extension(self):
        post = self.make_post(files=[upload("slides.pdf", b"<script>alert(1)</script>", "text/html"),
                                     upload("photo.JPG", b"\xff\xd8\xff", "application/x-evil")])
        self.assertEqual([a["contentType"] for a in post["attachments"]], ["application/pdf", "image/jpeg"])
        self.assertEqual(
            set(Attachment.objects.values_list("content_type", flat=True)), {"application/pdf", "image/jpeg"}
        )

    def test_unsupported_extension_rejected(self):
        for name in ("run.exe", "page.html", "image.svg", "noextension", "archive.pdf.exe"):
            with self.subTest(name=name):
                self.assertFieldErrors(self.create(files=[upload(name, b"data", "application/pdf")]), "files")
        self.assertFalse(Post.objects.exists())
        self.assertFalse(Attachment.objects.exists())

    def test_oversized_file_rejected(self):
        response = self.create(files=[upload("big.pdf", b"x" * (10 * MB + 1))])
        body = self.assertFieldErrors(response, "files")
        self.assertIn("10 MB", body["message"])
        self.assertFalse(Post.objects.exists())

    def test_file_of_exactly_10_mb_accepted(self):
        post = self.make_post(files=[upload("big.pdf", b"x" * (10 * MB))])
        self.assertEqual(post["attachments"][0]["size"], 10 * MB)

    def test_empty_file_rejected(self):
        self.assertFieldErrors(self.create(files=[upload("empty.txt", b"")]), "files")
        self.assertFalse(Post.objects.exists())

    def test_at_most_five_files(self):
        files = [upload(f"f{i}.txt", b"x") for i in range(6)]
        self.assertFieldErrors(self.create(files=files), "files")
        self.assertFalse(Post.objects.exists())
        post = self.make_post(files=[upload(f"f{i}.txt", b"x") for i in range(5)])
        self.assertEqual(len(post["attachments"]), 5)

    def test_path_like_names_reduced_to_basename(self):
        post = self.make_post(files=[upload("../../etc/passwd.txt", b"x"),
                                     upload("C:\\Users\\me\\Desktop\\plan.docx", b"x")])
        self.assertEqual([a["name"] for a in post["attachments"]], ["passwd.txt", "plan.docx"])

    def test_long_names_are_shortened_keeping_the_extension(self):
        post = self.make_post(files=[upload("x" * 250 + ".docx", b"x")])
        name = post["attachments"][0]["name"]
        self.assertEqual(len(name), 200)
        self.assertTrue(name.endswith(".docx"))
        self.assertEqual(post["attachments"][0]["contentType"], FILE_TYPES[".docx"])

    def test_bad_file_after_good_one_saves_nothing(self):
        response = self.create(files=[upload("ok.txt", b"x"), upload("bad.exe", b"x")])
        self.assertFieldErrors(response, "files")
        self.assertFalse(Post.objects.exists())
        self.assertFalse(Attachment.objects.exists())


# --------------------------------------------------------------------------- #
# Who can see what                                                             #
# --------------------------------------------------------------------------- #


class VisibilityTests(BoardTestCase):
    def setUp(self):
        super().setUp()
        self.all_students = [self.st_c1, self.st_c2, self.st_c3, self.st_c4, self.st_c5, self.unplaced,
                             self.other_student]

    def assertVisibleTo(self, post, visible):
        attachment = post["attachments"][0]["id"]
        for student in self.all_students:
            with self.subTest(audience=post["audience"]["label"], student=student.name):
                listed = post["id"] in self.ids(self.api_get(POSTS, user=student))
                detail = self.api_get(post_url(post["id"]), user=student)
                download = self.download(attachment_url(post["id"], attachment), student)
                if student in visible:
                    self.assertTrue(listed)
                    self.assertStatus(detail, 200)
                    self.assertStatus(download, 200)
                    self.assertEqual(download.content, b"%PDF-1.4 hello")
                else:
                    self.assertFalse(listed)
                    self.assertStatus(detail, 404)
                    self.assertStatus(download, 404)
                    self.assertStatus(self.api_post(read_url(post["id"]), user=student), 404)

    def test_batch_post(self):
        post = self.make_post(node=self.b1, files=[upload()])
        self.assertVisibleTo(post, [self.st_c1, self.st_c2, self.st_c3, self.st_c4])

    def test_department_post(self):
        post = self.make_post(node=self.d1, files=[upload()])
        self.assertVisibleTo(post, [self.st_c1, self.st_c2, self.st_c3])

    def test_section_post(self):
        post = self.make_post(node=self.s1, files=[upload()])
        self.assertVisibleTo(post, [self.st_c1, self.st_c2])

    def test_cohort_post(self):
        post = self.make_post(node=self.c1, files=[upload()])
        self.assertVisibleTo(post, [self.st_c1])

    def test_other_batch_post(self):
        post = self.make_post(node=self.b2, files=[upload()])
        self.assertVisibleTo(post, [self.st_c5])

    def test_other_tenant_post_only_visible_there(self):
        response = self.multipart(POSTS, {"kind": "note", "title": "Theirs", "audienceLevel": "batch",
                                          "audienceId": str(self.other_batch.pk), "files": [upload()]},
                                  self.other_admin)
        self.assertStatus(response, 201)
        self.assertVisibleTo(response.json()["post"], [self.other_student])

    def test_student_view_has_no_staff_fields(self):
        post = self.make_post(node=self.c1)
        data = self.api_get(post_url(post["id"]), user=self.st_c1).json()["post"]
        self.assertIs(data["read"], False)
        for field in ("canEdit", "readers", "audienceSize"):
            self.assertNotIn(field, data)

    def test_moving_a_student_changes_what_they_see(self):
        section_post = self.make_post(node=self.s1, title="For section A")
        other_post = self.make_post(node=self.s2, title="For section B")
        self.assertEqual(self.ids(self.api_get(POSTS, user=self.st_c1)), [section_post["id"]])

        response = self.api_patch(f"{USERS}/{self.st_c1.pk}", {"cohortId": str(self.c3.pk)}, user=self.admin)
        self.assertStatus(response, 200)
        self.assertEqual(self.ids(self.api_get(POSTS, user=self.st_c1)), [other_post["id"]])
        self.assertStatus(self.api_get(post_url(section_post["id"]), user=self.st_c1), 404)
        self.assertStatus(self.api_get(post_url(other_post["id"]), user=self.st_c1), 200)

        # Placing a previously unplaced student shows them their group's posts.
        self.assertEqual(self.ids(self.api_get(POSTS, user=self.unplaced)), [])
        response = self.api_patch(f"{USERS}/{self.unplaced.pk}", {"cohortId": str(self.c2.pk)}, user=self.admin)
        self.assertStatus(response, 200)
        self.assertEqual(self.ids(self.api_get(POSTS, user=self.unplaced)), [section_post["id"]])


# --------------------------------------------------------------------------- #
# Staff listing                                                                #
# --------------------------------------------------------------------------- #


class StaffListingTests(BoardTestCase):
    def setUp(self):
        super().setUp()
        self.p_batch = self.make_post(self.educator, self.b1, title="Batch welcome", body="Hello everyone",
                                      kind="message")
        self.p_dept = self.make_post(self.other_educator, self.d1, title="CSE timetable", body="See attached",
                                     kind="note")
        self.p_section = self.make_post(self.admin, self.s1, title="Section A test", body="Thursday quiz",
                                        kind="message")
        self.p_cohort = self.make_post(self.educator, self.c1, title="Lab 1 kit", body="Bring goggles",
                                       kind="note")
        self.p_other_batch = self.make_post(self.educator, self.b2, title="Batch two", body="Hi", kind="message")
        for minutes, post in enumerate([self.p_other_batch, self.p_cohort, self.p_section, self.p_dept,
                                        self.p_batch]):
            self.age(post["id"], minutes + 1)  # p_other_batch is the newest
        self.newest_first = [self.p_other_batch, self.p_cohort, self.p_section, self.p_dept, self.p_batch]

    def listing(self, user=None, **params):
        return self.api_get(POSTS, params=params, user=user or self.educator)

    def test_staff_see_every_post_newest_first(self):
        for user in (self.admin, self.educator, self.other_educator):
            with self.subTest(role=user.role, name=user.name):
                response = self.listing(user)
                self.assertEqual(self.ids(response), [p["id"] for p in self.newest_first])
                self.assertEqual(response.json()["total"], 5)

    def test_pinned_first(self):
        response = self.api_patch(post_url(self.p_batch["id"]), {"pinned": True}, user=self.admin)
        self.assertStatus(response, 200)
        self.assertEqual(self.ids(self.listing()),
                         [self.p_batch["id"], *[p["id"] for p in self.newest_first[:-1]]])

    def test_tenant_isolation(self):
        self.assertEqual(self.ids(self.listing(self.other_admin)), [])
        self.assertEqual(self.listing(self.other_admin).json()["total"], 0)

    def test_filter_by_kind(self):
        self.assertEqual(set(self.ids(self.listing(kind="note"))), {self.p_dept["id"], self.p_cohort["id"]})
        self.assertEqual(len(self.ids(self.listing(kind="message"))), 3)
        self.assertStatus(self.listing(kind="poll"), 400)

    def test_filter_mine(self):
        self.assertEqual(set(self.ids(self.listing(self.educator, mine="true"))),
                         {self.p_batch["id"], self.p_cohort["id"], self.p_other_batch["id"]})
        self.assertEqual(self.ids(self.listing(self.admin, mine="true")), [self.p_section["id"]])
        self.assertEqual(len(self.ids(self.listing(self.educator, mine="false"))), 5)

    def test_search(self):
        self.assertEqual(self.ids(self.listing(q="timetable")), [self.p_dept["id"]])
        self.assertEqual(self.ids(self.listing(q="GOGGLES")), [self.p_cohort["id"]])
        self.assertEqual(set(self.ids(self.listing(q="batch"))), {self.p_batch["id"], self.p_other_batch["id"]})
        self.assertEqual(self.ids(self.listing(q="nothing like this")), [])
        self.assertStatus(self.listing(q="bad\x00"), 400)

    def test_group_filters_select_posts_at_or_under_the_group(self):
        b, d, s, c, o = self.p_batch, self.p_dept, self.p_section, self.p_cohort, self.p_other_batch
        cases = [
            ("batch", self.b1, [b, d, s, c]),
            ("batch", self.b2, [o]),
            ("department", self.d1, [d, s, c]),
            ("department", self.d2, []),
            ("section", self.s1, [s, c]),
            ("section", self.s2, []),
            ("cohort", self.c1, [c]),
            ("cohort", self.c2, []),
        ]
        for level, node, expected in cases:
            with self.subTest(level=level, node=node.name):
                response = self.listing(**{level: str(node.pk)})
                self.assertEqual(set(self.ids(response)), {p["id"] for p in expected})
                self.assertEqual(response.json()["total"], len(expected))

    def test_unknown_group_filter_is_400(self):
        for level, value in [("batch", str(ObjectId())), ("department", "nope"), ("section", str(self.b1.pk)),
                             ("cohort", str(self.other_cohort.pk)), ("batch", str(self.other_batch.pk))]:
            with self.subTest(level=level, value=value):
                self.assertStatus(self.listing(**{level: value}), 400)

    def test_filters_combine(self):
        response = self.listing(self.educator, batch=str(self.b1.pk), kind="note", mine="true")
        self.assertEqual(self.ids(response), [self.p_cohort["id"]])

    def test_pagination(self):
        expected = [p["id"] for p in self.newest_first]
        first = self.listing(limit=2)
        self.assertEqual(self.ids(first), expected[:2])
        self.assertEqual(first.json()["total"], 5)
        self.assertEqual(self.ids(self.listing(limit=2, offset=2)), expected[2:4])
        last = self.listing(limit=2, offset=4)
        self.assertEqual(self.ids(last), expected[4:])
        self.assertEqual(last.json()["total"], 5)
        self.assertEqual(self.ids(self.listing(offset=10)), [])
        # Bad values fall back to defaults / are clamped.
        self.assertEqual(self.ids(self.listing(limit="abc", offset="xyz")), expected)
        self.assertEqual(len(self.ids(self.listing(limit=0))), 1)
        self.assertEqual(self.ids(self.listing(offset=-3)), expected)

    def test_listing_includes_attachments_without_contents(self):
        response = self.multipart(attachments_url(self.p_batch["id"]), {"files": [upload("a.pdf")]}, self.educator)
        self.assertStatus(response, 201)
        posts = {p["id"]: p for p in self.listing().json()["posts"]}
        self.assertEqual(posts[self.p_batch["id"]]["attachments"][0]["name"], "a.pdf")
        self.assertNotIn("data", posts[self.p_batch["id"]]["attachments"][0])
        self.assertEqual(posts[self.p_dept["id"]]["attachments"], [])

    def test_can_edit_flag(self):
        flags = {p["id"]: p["canEdit"] for p in self.listing(self.educator).json()["posts"]}
        self.assertEqual(flags, {
            self.p_batch["id"]: True, self.p_dept["id"]: False, self.p_section["id"]: False,
            self.p_cohort["id"]: True, self.p_other_batch["id"]: True,
        })
        self.assertTrue(all(p["canEdit"] for p in self.listing(self.admin).json()["posts"]))


# --------------------------------------------------------------------------- #
# Student listing and read state                                               #
# --------------------------------------------------------------------------- #


class StudentReadTests(BoardTestCase):
    def test_student_listing_and_read_flags(self):
        first = self.make_post(node=self.b1, title="First")
        second = self.make_post(node=self.c1, title="Second", kind="note")
        self.make_post(node=self.c3, title="Not for st_c1")
        self.age(first["id"], 2)
        self.age(second["id"], 1)

        response = self.api_get(POSTS, user=self.st_c1)
        self.assertEqual(self.ids(response), [second["id"], first["id"]])
        self.assertEqual(response.json()["total"], 2)
        self.assertEqual([p["read"] for p in response.json()["posts"]], [False, False])
        self.assertEqual(self.api_get(UNREAD, user=self.st_c1).json(), {"unread": 2})

        response = self.api_post(read_url(first["id"]), user=self.st_c1)
        self.assertStatus(response, 200)
        self.assertEqual(response.json(), {"read": True})
        reads = {p["id"]: p["read"] for p in self.api_get(POSTS, user=self.st_c1).json()["posts"]}
        self.assertEqual(reads, {first["id"]: True, second["id"]: False})
        self.assertIs(self.api_get(post_url(first["id"]), user=self.st_c1).json()["post"]["read"], True)
        self.assertEqual(self.api_get(UNREAD, user=self.st_c1).json(), {"unread": 1})

        # Idempotent.
        self.assertStatus(self.api_post(read_url(first["id"]), user=self.st_c1), 200)
        self.assertEqual(PostRead.objects.filter(post_id=first["id"], user=self.st_c1).count(), 1)
        self.assertEqual(self.api_get(UNREAD, user=self.st_c1).json(), {"unread": 1})

        self.assertStatus(self.api_post(read_url(second["id"]), user=self.st_c1), 200)
        self.assertEqual(self.api_get(UNREAD, user=self.st_c1).json(), {"unread": 0})
        # Another student's reads are independent.
        self.assertEqual(self.api_get(UNREAD, user=self.st_c2).json(), {"unread": 1})

    def test_student_filters(self):
        note = self.make_post(node=self.b1, title="Reading list", kind="note", body="Chapter 3")
        message = self.make_post(node=self.c1, title="Reminder", kind="message", body="Lab tomorrow")
        self.assertEqual(self.ids(self.api_get(POSTS, {"kind": "note"}, user=self.st_c1)), [note["id"]])
        self.assertEqual(self.ids(self.api_get(POSTS, {"q": "lab"}, user=self.st_c1)), [message["id"]])

    def test_unread_for_staff_and_unplaced(self):
        self.make_post(node=self.b1)
        for user in (self.admin, self.educator, self.unplaced):
            with self.subTest(name=user.name):
                response = self.api_get(UNREAD, user=user)
                self.assertStatus(response, 200)
                self.assertEqual(response.json(), {"unread": 0})

    def test_unread_ignores_other_groups_and_tenants(self):
        self.make_post(node=self.c3)
        self.make_post(node=self.b2)
        self.assertEqual(self.api_get(UNREAD, user=self.st_c1).json(), {"unread": 0})
        self.assertEqual(self.api_get(UNREAD, user=self.other_student).json(), {"unread": 0})


# --------------------------------------------------------------------------- #
# Staff statistics: audience size and readers                                  #
# --------------------------------------------------------------------------- #


class StaffStatsTests(BoardTestCase):
    def stats(self, post_id):
        data = self.api_get(post_url(post_id), user=self.educator).json()["post"]
        return data["audienceSize"], data["readers"]

    def test_audience_size_per_level(self):
        expected = {self.b1: 4, self.d1: 3, self.s1: 2, self.c1: 1, self.d2: 1, self.b2: 1}
        for node, size in expected.items():
            with self.subTest(level=node.LEVEL, node=node.name):
                post = self.make_post(node=node)
                self.assertEqual(post["audienceSize"], size)
        empty = make_cohort(self.inst, "Empty", section=self.s1)
        self.assertEqual(self.make_post(node=empty)["audienceSize"], 0)

    def test_readers_count_only_current_audience(self):
        post = self.make_post(node=self.s1)
        self.assertEqual(self.stats(post["id"]), (2, 0))
        self.api_post(read_url(post["id"]), user=self.st_c1)
        self.api_post(read_url(post["id"]), user=self.st_c2)
        self.assertEqual(self.stats(post["id"]), (2, 2))

        # st_c1 moves to the sibling section: no longer in the audience or a reader.
        response = self.api_patch(f"{USERS}/{self.st_c1.pk}", {"cohortId": str(self.c3.pk)}, user=self.admin)
        self.assertStatus(response, 200)
        self.assertEqual(self.stats(post["id"]), (1, 1))
        listed = {p["id"]: p for p in self.api_get(POSTS, user=self.admin).json()["posts"]}
        self.assertEqual((listed[post["id"]]["audienceSize"], listed[post["id"]]["readers"]), (1, 1))

        # Moving back counts them again (the read is kept).
        self.api_patch(f"{USERS}/{self.st_c1.pk}", {"cohortId": str(self.c2.pk)}, user=self.admin)
        self.assertEqual(self.stats(post["id"]), (2, 2))

    def test_readers_follow_audience_change(self):
        post = self.make_post(node=self.c1)
        self.api_post(read_url(post["id"]), user=self.st_c1)
        self.assertEqual(self.stats(post["id"]), (1, 1))
        response = self.api_patch(post_url(post["id"]), {"audience": {"level": "cohort", "id": str(self.c2.pk)}},
                                  user=self.educator)
        self.assertStatus(response, 200)
        self.assertEqual(self.stats(post["id"]), (1, 0))
        self.api_patch(post_url(post["id"]), {"audience": {"level": "batch", "id": str(self.b1.pk)}},
                       user=self.educator)
        self.assertEqual(self.stats(post["id"]), (4, 1))


# --------------------------------------------------------------------------- #
# Editing                                                                      #
# --------------------------------------------------------------------------- #


class UpdateTests(BoardTestCase):
    def setUp(self):
        super().setUp()
        self.post = self.make_post(self.educator, self.s1, title="Original", body="Body")

    def patch(self, body, user=None):
        return self.api_patch(post_url(self.post["id"]), body, user=user or self.educator)

    def test_edit_title_and_body_sets_edited_at(self):
        response = self.patch({"title": "  New   title ", "body": " New body "})
        self.assertStatus(response, 200)
        post = response.json()["post"]
        self.assertEqual((post["title"], post["body"]), ("New title", "New body"))
        self.assertIsNotNone(post["editedAt"])
        stored = Post.objects.get(pk=self.post["id"])
        self.assertEqual((stored.title, stored.body), ("New title", "New body"))
        self.assertIsNotNone(stored.edited_at)

    def test_body_only_edit_sets_edited_at(self):
        response = self.patch({"body": "Changed"})
        self.assertIsNotNone(response.json()["post"]["editedAt"])

    def test_unchanged_values_do_not_set_edited_at(self):
        response = self.patch({"title": "Original", "body": "Body"})
        self.assertStatus(response, 200)
        self.assertIsNone(response.json()["post"]["editedAt"])

    def test_pin_does_not_set_edited_at(self):
        response = self.patch({"pinned": True})
        self.assertStatus(response, 200)
        self.assertIs(response.json()["post"]["pinned"], True)
        self.assertIsNone(response.json()["post"]["editedAt"])
        self.assertTrue(Post.objects.get(pk=self.post["id"]).pinned)
        response = self.patch({"pinned": False})
        self.assertIs(response.json()["post"]["pinned"], False)
        self.assertIsNone(Post.objects.get(pk=self.post["id"]).edited_at)

    def test_change_audience(self):
        response = self.patch({"audience": {"level": "cohort", "id": str(self.c3.pk)}})
        self.assertStatus(response, 200)
        audience = response.json()["post"]["audience"]
        self.assertEqual((audience["level"], audience["id"]), ("cohort", str(self.c3.pk)))
        stored = Post.objects.get(pk=self.post["id"])
        self.assertEqual((stored.batch_id, stored.department_id, stored.section_id, stored.cohort_id),
                         (self.b1.pk, self.d1.pk, self.s2.pk, self.c3.pk))
        self.assertIsNone(response.json()["post"]["editedAt"])
        # Visibility follows.
        self.assertStatus(self.api_get(post_url(self.post["id"]), user=self.st_c1), 404)
        self.assertStatus(self.api_get(post_url(self.post["id"]), user=self.st_c3), 200)

        # Moving up to a batch clears the deeper levels.
        response = self.patch({"audience": {"level": "batch", "id": str(self.b2.pk)}})
        self.assertStatus(response, 200)
        stored = Post.objects.get(pk=self.post["id"])
        self.assertEqual((stored.batch_id, stored.department_id, stored.section_id, stored.cohort_id),
                         (self.b2.pk, None, None, None))

    def test_bad_values_are_field_errors(self):
        cases = [
            ({"title": ""}, "title"),
            ({"title": "x" * 201}, "title"),
            ({"title": 5}, "title"),
            ({"title": None}, "title"),
            ({"body": "x" * 10_001}, "body"),
            ({"body": ["list"]}, "body"),
            ({"pinned": "yes"}, "pinned"),
            ({"pinned": 1}, "pinned"),
            ({"audience": "batch"}, "audience"),
            ({"audience": {"level": "batch"}}, "audience"),
            ({"audience": {"level": "batch", "id": "nope"}}, "audience"),
            ({"audience": {"level": "cohort", "id": str(self.s1.pk)}}, "audience"),
            ({"audience": {"level": "batch", "id": str(self.other_batch.pk)}}, "audience"),
        ]
        for body, field in cases:
            with self.subTest(body=str(body)[:60]):
                self.assertFieldErrors(self.patch(body), field)
        self.assertFieldErrors(self.patch({"title": "", "body": "x" * 10_001, "pinned": "no"}),
                               "title", "body", "pinned")
        stored = Post.objects.get(pk=self.post["id"])
        self.assertEqual((stored.title, stored.body, stored.pinned, stored.section_id),
                         ("Original", "Body", False, self.s1.pk))

    def test_valid_change_not_saved_when_another_field_is_bad(self):
        self.assertFieldErrors(self.patch({"title": "Fine", "pinned": "nope"}), "pinned")
        self.assertEqual(Post.objects.get(pk=self.post["id"]).title, "Original")

    def test_body_must_be_json(self):
        response = self.request("PATCH", post_url(self.post["id"]), user=self.educator, raw="title=x")
        self.assertStatus(response, 400)
        response = self.client.patch(post_url(self.post["id"]), "title=x", content_type="text/plain",
                                     HTTP_AUTHORIZATION=f"Bearer {create_token(self.educator)}")
        self.assertStatus(response, 400)

    def test_message_body_may_be_cleared(self):
        # Only creation requires text or a file; an edit may leave a title only.
        response = self.patch({"body": ""})
        self.assertStatus(response, 200)
        self.assertEqual(response.json()["post"]["body"], "")


# --------------------------------------------------------------------------- #
# Attachments                                                                  #
# --------------------------------------------------------------------------- #


class AttachmentTests(BoardTestCase):
    def test_download(self):
        content = b"%PDF-1.4\n\x00\x01\x02 binary \xff"
        post = self.make_post(node=self.c1, files=[upload("résumé notes.pdf", content, "text/html")])
        attachment = post["attachments"][0]
        self.assertEqual(attachment["name"], "résumé notes.pdf")
        for user in (self.st_c1, self.educator, self.admin):
            with self.subTest(role=user.role):
                response = self.download(attachment_url(post["id"], attachment["id"]), user)
                self.assertStatus(response, 200)
                self.assertEqual(response.content, content)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertEqual(response["Content-Disposition"],
                                 "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9%20notes.pdf")
                self.assertEqual(response["Content-Disposition"],
                                 f"attachment; filename*=UTF-8''{quote('résumé notes.pdf')}")
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                self.assertIn("sandbox", response["Content-Security-Policy"])
                self.assertIn("default-src 'none'", response["Content-Security-Policy"])
                self.assertIn("no-store", response["Cache-Control"])

    def test_attachment_of_another_post_is_404(self):
        first = self.make_post(node=self.c1, files=[upload("a.pdf")])
        second = self.make_post(node=self.c1, files=[upload("b.pdf")])
        wrong = attachment_url(second["id"], first["attachments"][0]["id"])
        self.assertStatus(self.download(wrong, self.st_c1), 404)
        self.assertStatus(self.download(wrong, self.admin), 404)
        self.assertStatus(self.api_delete(wrong, user=self.admin), 404)
        self.assertEqual(Attachment.objects.count(), 2)

    def test_add_attachments(self):
        post = self.make_post(self.educator, self.c1, files=[upload("a.pdf")])
        self.assertIsNone(post["editedAt"])
        response = self.multipart(attachments_url(post["id"]),
                                  {"files": [upload("b.png", b"\x89PNG", "text/plain"), upload("dir/c.csv", b"a,b")]},
                                  self.educator)
        self.assertStatus(response, 201)
        data = response.json()["post"]
        self.assertEqual([(a["name"], a["contentType"]) for a in data["attachments"]],
                         [("a.pdf", "application/pdf"), ("b.png", "image/png"), ("c.csv", "text/csv")])
        self.assertIsNotNone(data["editedAt"])

    def test_add_attachments_validation(self):
        post = self.make_post(self.educator, self.c1, files=[upload(f"{i}.txt", b"x") for i in range(4)])
        url = attachments_url(post["id"])
        self.assertFieldErrors(self.multipart(url, {}, self.educator), "files")
        self.assertFieldErrors(self.multipart(url, {"files": [upload("x.txt", b"x"), upload("y.txt", b"y")]},
                                              self.educator), "files")
        self.assertFieldErrors(self.multipart(url, {"files": [upload("x.exe", b"x")]}, self.educator), "files")
        self.assertFieldErrors(self.multipart(url, {"files": [upload("x.txt", b"")]}, self.educator), "files")
        self.assertFieldErrors(self.multipart(url, {"files": [upload("x.pdf", b"x" * (10 * MB + 1))]},
                                              self.educator), "files")
        self.assertEqual(Attachment.objects.filter(post_id=post["id"]).count(), 4)
        self.assertIsNone(Post.objects.get(pk=post["id"]).edited_at)

        self.assertStatus(self.multipart(url, {"files": [upload("five.txt", b"x")]}, self.educator), 201)
        self.assertFieldErrors(self.multipart(url, {"files": [upload("six.txt", b"x")]}, self.educator), "files")
        self.assertEqual(Attachment.objects.filter(post_id=post["id"]).count(), 5)

    def test_add_attachments_to_unknown_post(self):
        response = self.multipart(attachments_url(str(ObjectId())), {"files": [upload()]}, self.admin)
        self.assertStatus(response, 404)

    def test_delete_attachment(self):
        post = self.make_post(self.educator, self.c1, files=[upload("a.pdf"), upload("b.pdf")])
        first, second = (a["id"] for a in post["attachments"])
        self.assertStatus(self.api_delete(attachment_url(post["id"], first), user=self.educator), 204)
        self.assertFalse(Attachment.objects.filter(pk=first).exists())
        self.assertTrue(Attachment.objects.filter(pk=second).exists())
        self.assertIsNotNone(Post.objects.get(pk=post["id"]).edited_at)
        self.assertStatus(self.download(attachment_url(post["id"], first), self.st_c1), 404)
        self.assertStatus(self.api_delete(attachment_url(post["id"], first), user=self.educator), 404)
        data = self.api_get(post_url(post["id"]), user=self.educator).json()["post"]
        self.assertEqual([a["id"] for a in data["attachments"]], [second])


# --------------------------------------------------------------------------- #
# Deleting                                                                     #
# --------------------------------------------------------------------------- #


class DeleteTests(BoardTestCase):
    def test_delete_post_removes_attachments_and_reads(self):
        post = self.make_post(self.educator, self.s1, title="Going away", files=[upload("a.pdf"), upload("b.txt")])
        keep = self.make_post(self.educator, self.s1, files=[upload("keep.pdf")])
        for student in (self.st_c1, self.st_c2):
            self.api_post(read_url(post["id"]), user=student)
        self.api_post(read_url(keep["id"]), user=self.st_c1)
        self.assertEqual(PostRead.objects.count(), 3)

        self.assertStatus(self.api_delete(post_url(post["id"]), user=self.educator), 204)
        self.assertFalse(Post.objects.filter(pk=post["id"]).exists())
        self.assertFalse(Attachment.objects.filter(post_id=post["id"]).exists())
        self.assertFalse(PostRead.objects.filter(post_id=post["id"]).exists())
        self.assertEqual(Attachment.objects.filter(post_id=keep["id"]).count(), 1)
        self.assertEqual(PostRead.objects.filter(post_id=keep["id"]).count(), 1)

        log = AuditLog.objects.get(action="post.deleted")
        self.assertEqual(log.actor_id, self.educator.pk)
        self.assertIn("Going away", log.summary)
        self.assertStatus(self.api_get(post_url(post["id"]), user=self.educator), 404)
        self.assertEqual(self.api_get(UNREAD, user=self.st_c2).json(), {"unread": 1})

    def test_delete_group_refuses_a_group_with_posts(self):
        empty_cohort = make_cohort(self.inst, "Empty", section=self.s1)
        post = self.make_post(self.admin, empty_cohort)
        url = f"{STRUCTURE}/cohort/{empty_cohort.pk}"
        response = self.api_delete(url, user=self.admin)
        self.assertStatus(response, 400)
        self.assertIn("notes or messages", response.json()["message"])
        self.assertTrue(type(empty_cohort).objects.filter(pk=empty_cohort.pk).exists())

        self.assertStatus(self.api_delete(post_url(post["id"]), user=self.admin), 204)
        self.assertStatus(self.api_delete(url, user=self.admin), 204)
        self.assertFalse(type(empty_cohort).objects.filter(pk=empty_cohort.pk).exists())

    def test_delete_group_refuses_a_batch_with_posts(self):
        batch = make_batch(self.inst, "2030")
        self.make_post(self.admin, batch)
        response = self.api_delete(f"{STRUCTURE}/batch/{batch.pk}", user=self.admin)
        self.assertStatus(response, 400)
        self.assertTrue(type(batch).objects.filter(pk=batch.pk).exists())
