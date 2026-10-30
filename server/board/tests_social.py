"""Tests for comments and reactions on notes and messages (/api/board/).

Reuses the fixture structure from board/tests.py (BoardTestCase):

    batch b1 ── department d1 ── section s1 ── cohorts c1 (st_c1), c2 (st_c2)
                              └─ section s2 ── cohort  c3 (st_c3)
             └─ department d2 ── section s3 ── cohort  c4 (st_c4)
    batch b2 ── ... ── cohort c5 (st_c5)
    an unplaced student, and a second institution (other_admin, other_student).
"""
from datetime import timedelta

from bson import ObjectId
from django.db import connection
from django.utils import timezone

from accounts.auth import create_token
from board.models import Comment, Post, PostRead, Reaction
from board.tests import POSTS, UNREAD, BoardTestCase, post_url

KINDS = list(Reaction.KINDS)


def comments_url(post_id):
    return f"{POSTS}/{post_id}/comments"


def comment_url(post_id, comment_id):
    return f"{POSTS}/{post_id}/comments/{comment_id}"


def reaction_url(post_id, kind):
    return f"{POSTS}/{post_id}/reactions/{kind}"


class SocialTestCase(BoardTestCase):
    def comment(self, post_id, user, body="Nice one"):
        return self.api_post(comments_url(post_id), {"body": body}, user=user)

    def add_comment(self, post_id, user, body="Nice one"):
        response = self.comment(post_id, user, body)
        self.assertStatus(response, 201)
        return response.json()["comment"]

    def list_comments(self, post_id, user, **params):
        response = self.api_get(comments_url(post_id), params=params, user=user)
        self.assertStatus(response, 200)
        return response.json()

    def react(self, post_id, kind, user):
        return self.api_put(reaction_url(post_id, kind), user=user)

    def unreact(self, post_id, kind, user):
        return self.api_delete(reaction_url(post_id, kind), user=user)

    def detail(self, post_id, user):
        response = self.api_get(post_url(post_id), user=user)
        self.assertStatus(response, 200)
        return response.json()["post"]

    def listed(self, post_id, user):
        response = self.api_get(POSTS, user=user)
        self.assertStatus(response, 200)
        return next(p for p in response.json()["posts"] if p["id"] == post_id)

    def unread(self, user):
        response = self.api_get(UNREAD, user=user)
        self.assertStatus(response, 200)
        return response.json()["unread"]

    def age_comment(self, comment_id, minutes):
        Comment.objects.filter(pk=comment_id).update(created_at=timezone.now() - timedelta(minutes=minutes))


# --------------------------------------------------------------------------- #
# Access control                                                               #
# --------------------------------------------------------------------------- #


class SocialAccessTests(SocialTestCase):
    def endpoints(self, post_id, comment_id):
        return [
            ("GET", comments_url(post_id)),
            ("POST", comments_url(post_id)),
            ("DELETE", comment_url(post_id, comment_id)),
            ("PUT", reaction_url(post_id, "like")),
            ("DELETE", reaction_url(post_id, "like")),
        ]

    def call(self, method, path, user):
        if method == "POST":
            return self.api_post(path, {"body": "Hi"}, user=user)
        if method == "DELETE":
            return self.api_delete(path, user=user)
        return self.request(method, path, user=user)

    def test_unauthenticated_requests_are_401(self):
        post = self.make_post(node=self.c1)
        comment = self.add_comment(post["id"], self.st_c1)
        for method, path in self.endpoints(post["id"], comment["id"]):
            with self.subTest(method=method, path=path):
                self.assertStatus(self.request(method, path), 401)
                self.assertStatus(self.request(method, path, token="not-a-token"), 401)
        self.assertEqual(Comment.objects.count(), 1)
        self.assertFalse(Reaction.objects.exists())

    def test_audience_at_every_level_can_comment_and_react(self):
        for node, student in [(self.b1, self.st_c4), (self.d1, self.st_c3), (self.s1, self.st_c2),
                              (self.c1, self.st_c1)]:
            with self.subTest(level=node.LEVEL):
                post = self.make_post(node=node)
                self.assertStatus(self.comment(post["id"], student), 201)
                self.assertEqual(self.list_comments(post["id"], student)["total"], 1)
                self.assertStatus(self.react(post["id"], "like", student), 200)
                self.assertStatus(self.unreact(post["id"], "like", student), 200)

    def test_all_staff_can_comment_and_react(self):
        post = self.make_post(self.educator, node=self.c1)
        for user in (self.admin, self.educator, self.other_educator):
            with self.subTest(role=user.role, name=user.name):
                self.assertStatus(self.comment(post["id"], user), 201)
                self.assertStatus(self.react(post["id"], "love", user), 200)
        self.assertEqual(self.list_comments(post["id"], self.other_educator)["total"], 3)
        self.assertEqual(self.detail(post["id"], self.admin)["reactions"],
                         [{"kind": "love", "count": 3, "mine": True}])

    def test_outsiders_get_404_everywhere(self):
        cases = [
            (self.s1, [self.st_c3, self.st_c4, self.st_c5, self.unplaced, self.other_student, self.other_admin]),
            (self.b1, [self.st_c5, self.unplaced, self.other_student, self.other_admin]),
            (self.c1, [self.st_c2, self.unplaced, self.other_admin]),
        ]
        for node, outsiders in cases:
            post = self.make_post(node=node)
            comment = self.add_comment(post["id"], self.admin)
            self.react(post["id"], "like", self.admin)
            for user in outsiders:
                for method, path in self.endpoints(post["id"], comment["id"]):
                    with self.subTest(level=node.LEVEL, user=user.name, method=method, path=path):
                        self.assertStatus(self.call(method, path, user), 404)
        self.assertEqual(Comment.objects.count(), 3)
        self.assertEqual(Reaction.objects.count(), 3)
        self.assertFalse(PostRead.objects.exists())

    def test_unknown_and_malformed_post_ids_are_404(self):
        for post_id in ("nope", str(ObjectId())):
            for method, path in self.endpoints(post_id, str(ObjectId())):
                with self.subTest(method=method, path=path):
                    self.assertStatus(self.call(method, path, self.admin), 404)

    def test_methods_not_allowed(self):
        post = self.make_post()
        comment = self.add_comment(post["id"], self.admin)
        self.assertStatus(self.api_put(comments_url(post["id"]), {}, user=self.admin), 405)
        self.assertStatus(self.api_get(comment_url(post["id"], comment["id"]), user=self.admin), 405)
        self.assertStatus(self.api_patch(comment_url(post["id"], comment["id"]), {}, user=self.admin), 405)
        self.assertStatus(self.api_get(reaction_url(post["id"], "like"), user=self.admin), 405)
        self.assertStatus(self.api_post(reaction_url(post["id"], "like"), {}, user=self.admin), 405)


# --------------------------------------------------------------------------- #
# Adding comments                                                              #
# --------------------------------------------------------------------------- #


class AddCommentTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.post = self.make_post(self.educator, node=self.s1)

    def test_comment_response(self):
        response = self.comment(self.post["id"], self.st_c1, "  Thanks, very helpful!  \n")
        self.assertStatus(response, 201)
        comment = response.json()["comment"]
        self.assertEqual(comment["body"], "Thanks, very helpful!")
        self.assertEqual(comment["author"], {"id": str(self.st_c1.pk), "name": "Stu One", "role": "student"})
        self.assertIs(comment["mine"], True)
        self.assertIs(comment["canDelete"], True)
        self.assertTrue(comment["createdAt"])
        stored = Comment.objects.get(pk=comment["id"])
        self.assertEqual((stored.post_id, stored.author_id, stored.body),
                         (Post.objects.get(pk=self.post["id"]).pk, self.st_c1.pk, "Thanks, very helpful!"))

    def test_inner_whitespace_and_newlines_kept(self):
        comment = self.add_comment(self.post["id"], self.st_c1, "Line one\n\n  Line   two")
        self.assertEqual(comment["body"], "Line one\n\n  Line   two")

    def test_staff_comment_author_fields(self):
        comment = self.add_comment(self.post["id"], self.educator, "Welcome")
        self.assertEqual(comment["author"], {"id": str(self.educator.pk), "name": "Ed Educator", "role": "educator"})
        self.assertIs(comment["mine"], True)
        self.assertIs(comment["canDelete"], True)

    def test_body_is_required(self):
        for body in ({"body": ""}, {"body": "   \n\t "}, {"body": None}, {}):
            with self.subTest(body=body):
                self.assertFieldErrors(self.api_post(comments_url(self.post["id"]), body, user=self.st_c1), "body")
        self.assertFalse(Comment.objects.exists())

    def test_body_length_limit(self):
        self.assertStatus(self.comment(self.post["id"], self.st_c1, "x" * 2000), 201)
        # Surrounding whitespace is trimmed before the limit is checked.
        self.assertStatus(self.comment(self.post["id"], self.st_c1, "  " + "y" * 2000 + "  "), 201)
        self.assertFieldErrors(self.comment(self.post["id"], self.st_c1, "x" * 2001), "body")
        self.assertEqual(Comment.objects.count(), 2)

    def test_body_must_be_text(self):
        for value in (5, True, ["hi"], {"text": "hi"}):
            with self.subTest(value=value):
                self.assertFieldErrors(self.comment(self.post["id"], self.st_c1, value), "body")
        self.assertFalse(Comment.objects.exists())

    def test_request_must_be_a_json_object(self):
        path = comments_url(self.post["id"])
        self.assertStatus(self.request("POST", path, user=self.st_c1, raw="{not json"), 400)
        self.assertStatus(self.request("POST", path, user=self.st_c1, raw='["hi"]'), 400)
        self.assertStatus(self.request("POST", path, user=self.st_c1, raw='"hi"'), 400)
        response = self.client.post(path, "body=hi", content_type="text/plain",
                                    HTTP_AUTHORIZATION=f"Bearer {create_token(self.st_c1)}")
        self.assertStatus(response, 400)
        response = self.client.post(path, {"body": "hi"},
                                    HTTP_AUTHORIZATION=f"Bearer {create_token(self.st_c1)}")  # multipart
        self.assertStatus(response, 400)
        self.assertFalse(Comment.objects.exists())

    def test_disabled_comments_are_403_but_listing_works(self):
        self.add_comment(self.post["id"], self.st_c1, "Before")
        Post.objects.filter(pk=self.post["id"]).update(comments_enabled=False)
        for user in (self.st_c1, self.educator, self.admin):
            with self.subTest(role=user.role):
                self.assertStatus(self.comment(self.post["id"], user, "After"), 403)
        listing = self.list_comments(self.post["id"], self.st_c2)
        self.assertEqual([c["body"] for c in listing["comments"]], ["Before"])
        self.assertEqual(Comment.objects.count(), 1)
        # Reactions are not affected by the comments switch.
        self.assertStatus(self.react(self.post["id"], "like", self.st_c2), 200)

    def test_disabled_comments_still_404_for_outsiders(self):
        Post.objects.filter(pk=self.post["id"]).update(comments_enabled=False)
        self.assertStatus(self.comment(self.post["id"], self.st_c3), 404)

    def test_student_comment_marks_post_read(self):
        self.assertEqual(self.unread(self.st_c1), 1)
        self.assertIs(self.listed(self.post["id"], self.st_c1)["read"], False)
        self.add_comment(self.post["id"], self.st_c1)
        self.assertEqual(self.unread(self.st_c1), 0)
        self.assertIs(self.listed(self.post["id"], self.st_c1)["read"], True)
        # Commenting again on an already-read post is fine.
        self.add_comment(self.post["id"], self.st_c1)
        self.assertEqual(PostRead.objects.filter(user=self.st_c1).count(), 1)
        # Other students are unaffected.
        self.assertEqual(self.unread(self.st_c2), 1)

    def test_staff_comment_creates_no_read(self):
        for user in (self.admin, self.educator, self.other_educator):
            self.add_comment(self.post["id"], user)
        self.assertFalse(PostRead.objects.exists())
        self.assertEqual(self.detail(self.post["id"], self.educator)["readers"], 0)

    def test_failed_comment_does_not_mark_read(self):
        self.assertFieldErrors(self.comment(self.post["id"], self.st_c1, ""), "body")
        Post.objects.filter(pk=self.post["id"]).update(comments_enabled=False)
        self.assertStatus(self.comment(self.post["id"], self.st_c1), 403)
        self.assertFalse(PostRead.objects.exists())


# --------------------------------------------------------------------------- #
# Listing comments                                                             #
# --------------------------------------------------------------------------- #


class ListCommentTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.post = self.make_post(self.educator, node=self.d1)

    def test_empty(self):
        self.assertEqual(self.list_comments(self.post["id"], self.st_c1), {"comments": [], "total": 0})

    def test_oldest_first(self):
        first = self.add_comment(self.post["id"], self.st_c1, "first")
        second = self.add_comment(self.post["id"], self.educator, "second")
        third = self.add_comment(self.post["id"], self.st_c3, "third")
        self.age_comment(first["id"], 30)
        self.age_comment(second["id"], 20)
        self.age_comment(third["id"], 10)
        listing = self.list_comments(self.post["id"], self.st_c2)
        self.assertEqual([c["body"] for c in listing["comments"]], ["first", "second", "third"])
        self.assertEqual(listing["total"], 3)

    def test_order_follows_created_at_not_insertion(self):
        early = self.add_comment(self.post["id"], self.st_c1, "inserted first")
        late = self.add_comment(self.post["id"], self.st_c1, "inserted second")
        self.age_comment(early["id"], 5)
        self.age_comment(late["id"], 50)
        listing = self.list_comments(self.post["id"], self.st_c1)
        self.assertEqual([c["body"] for c in listing["comments"]], ["inserted second", "inserted first"])

    def test_pagination(self):
        made = [self.add_comment(self.post["id"], self.st_c1, f"c{i}") for i in range(7)]
        for i, comment in enumerate(made):
            self.age_comment(comment["id"], 100 - i)
        bodies = lambda **p: [c["body"] for c in self.list_comments(self.post["id"], self.st_c2, **p)["comments"]]
        self.assertEqual(bodies(), [f"c{i}" for i in range(7)])
        self.assertEqual(bodies(limit=3), ["c0", "c1", "c2"])
        self.assertEqual(bodies(offset=3, limit=3), ["c3", "c4", "c5"])
        self.assertEqual(bodies(offset=6, limit=3), ["c6"])
        self.assertEqual(bodies(offset=50), [])
        # Bad values fall back to defaults / are clamped.
        self.assertEqual(bodies(offset="x", limit="y"), [f"c{i}" for i in range(7)])
        self.assertEqual(bodies(offset=-5, limit=0), ["c0"])
        self.assertEqual(self.list_comments(self.post["id"], self.st_c2, offset=5, limit=1)["total"], 7)

    def test_default_page_is_50_and_max_is_100(self):
        Comment.objects.bulk_create(
            [Comment(post_id=Post.objects.get(pk=self.post["id"]).pk, author=self.st_c1, body=f"c{i}")
             for i in range(105)]
        )
        self.assertEqual(len(self.list_comments(self.post["id"], self.admin)["comments"]), 50)
        listing = self.list_comments(self.post["id"], self.admin, limit=500)
        self.assertEqual(len(listing["comments"]), 100)
        self.assertEqual(listing["total"], 105)

    def test_comments_of_other_posts_not_listed(self):
        other = self.make_post(self.educator, node=self.d1, title="Other")
        self.add_comment(self.post["id"], self.st_c1, "here")
        self.add_comment(other["id"], self.st_c1, "there")
        listing = self.list_comments(self.post["id"], self.st_c1)
        self.assertEqual([c["body"] for c in listing["comments"]], ["here"])
        self.assertEqual(listing["total"], 1)

    def test_listing_does_not_mark_read(self):
        self.add_comment(self.post["id"], self.educator)
        self.list_comments(self.post["id"], self.st_c1)
        self.assertEqual(self.unread(self.st_c1), 1)

    def test_comment_count_on_post_list_and_detail(self):
        other = self.make_post(self.educator, node=self.d1, title="Other")
        self.assertEqual(self.detail(self.post["id"], self.st_c1)["commentCount"], 0)
        self.assertEqual(self.listed(self.post["id"], self.admin)["commentCount"], 0)
        a = self.add_comment(self.post["id"], self.st_c1)
        self.add_comment(self.post["id"], self.st_c3)
        self.add_comment(self.post["id"], self.admin)
        self.add_comment(other["id"], self.st_c1)
        for user in (self.st_c1, self.st_c2, self.admin, self.educator):
            with self.subTest(user=user.name):
                self.assertEqual(self.detail(self.post["id"], user)["commentCount"], 3)
                self.assertEqual(self.listed(self.post["id"], user)["commentCount"], 3)
                self.assertEqual(self.listed(other["id"], user)["commentCount"], 1)
        self.assertStatus(self.api_delete(comment_url(self.post["id"], a["id"]), user=self.st_c1), 204)
        self.assertEqual(self.detail(self.post["id"], self.st_c1)["commentCount"], 2)
        self.assertEqual(self.listed(self.post["id"], self.st_c1)["commentCount"], 2)

    def test_mine_and_can_delete_flags_per_viewer(self):
        by_student = self.add_comment(self.post["id"], self.st_c1, "student")
        by_author = self.add_comment(self.post["id"], self.educator, "author")
        by_other_ed = self.add_comment(self.post["id"], self.other_educator, "other educator")
        by_admin = self.add_comment(self.post["id"], self.admin, "admin")
        for i, c in enumerate((by_student, by_author, by_other_ed, by_admin)):
            self.age_comment(c["id"], 10 - i)
        # viewer -> [(mine, canDelete)] for (student, author, other educator, admin)
        expected = {
            self.st_c1: [(True, True), (False, False), (False, False), (False, False)],
            self.st_c2: [(False, False)] * 4,
            self.educator: [(False, True), (True, True), (False, True), (False, True)],
            self.other_educator: [(False, False), (False, False), (True, True), (False, False)],
            self.admin: [(False, True), (False, True), (False, True), (True, True)],
        }
        for viewer, flags in expected.items():
            with self.subTest(viewer=viewer.name):
                listing = self.list_comments(self.post["id"], viewer)["comments"]
                self.assertEqual([(c["mine"], c["canDelete"]) for c in listing], flags)

    def test_author_details_in_listing(self):
        self.add_comment(self.post["id"], self.st_c3, "hi")
        comment = self.list_comments(self.post["id"], self.admin)["comments"][0]
        self.assertEqual(comment["author"], {"id": str(self.st_c3.pk), "name": "Stu Three", "role": "student"})
        self.assertEqual(set(comment), {"id", "body", "author", "createdAt", "mine", "canDelete"})


# --------------------------------------------------------------------------- #
# Deleting comments                                                            #
# --------------------------------------------------------------------------- #


class DeleteCommentTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.post = self.make_post(self.educator, node=self.s1)
        self.comment_by_student = self.add_comment(self.post["id"], self.st_c1, "student comment")

    def delete(self, user, comment_id=None, post_id=None):
        return self.api_delete(comment_url(post_id or self.post["id"], comment_id or self.comment_by_student["id"]),
                               user=user)

    def exists(self, comment_id=None):
        return Comment.objects.filter(pk=comment_id or self.comment_by_student["id"]).exists()

    def test_author_can_delete_own(self):
        self.assertStatus(self.delete(self.st_c1), 204)
        self.assertFalse(self.exists())
        # Deleting again is 404.
        self.assertStatus(self.delete(self.st_c1), 404)

    def test_another_student_cannot(self):
        self.assertStatus(self.delete(self.st_c2), 403)
        self.assertTrue(self.exists())

    def test_student_outside_audience_gets_404(self):
        self.assertStatus(self.delete(self.st_c3), 404)
        self.assertTrue(self.exists())

    def test_post_author_educator_can_moderate(self):
        self.assertStatus(self.delete(self.educator), 204)
        self.assertFalse(self.exists())

    def test_other_educator_cannot(self):
        self.assertStatus(self.delete(self.other_educator), 403)
        self.assertTrue(self.exists())

    def test_educator_can_delete_own_comment_on_others_post(self):
        mine = self.add_comment(self.post["id"], self.other_educator)
        self.assertStatus(self.delete(self.other_educator, mine["id"]), 204)
        self.assertFalse(self.exists(mine["id"]))

    def test_student_cannot_delete_staff_comment(self):
        staff = self.add_comment(self.post["id"], self.educator)
        self.assertStatus(self.delete(self.st_c1, staff["id"]), 403)
        self.assertTrue(self.exists(staff["id"]))

    def test_admin_can_delete_any(self):
        theirs = self.add_comment(self.post["id"], self.other_educator)
        self.assertStatus(self.delete(self.admin), 204)
        self.assertStatus(self.delete(self.admin, theirs["id"]), 204)
        self.assertFalse(Comment.objects.exists())

    def test_other_tenant_admin_gets_404(self):
        self.assertStatus(self.delete(self.other_admin), 404)
        self.assertTrue(self.exists())

    def test_wrong_post_or_bad_ids_are_404(self):
        other = self.make_post(self.educator, node=self.s1, title="Other")
        cases = [
            (other["id"], self.comment_by_student["id"]),  # comment belongs to a different post
            (self.post["id"], str(ObjectId())),
            (self.post["id"], "nope"),
            ("nope", self.comment_by_student["id"]),
            (str(ObjectId()), self.comment_by_student["id"]),
        ]
        for post_id, comment_id in cases:
            with self.subTest(post_id=post_id, comment_id=comment_id):
                self.assertStatus(self.delete(self.admin, comment_id, post_id), 404)
        self.assertTrue(self.exists())

    def test_deleting_a_comment_works_when_comments_are_disabled(self):
        Post.objects.filter(pk=self.post["id"]).update(comments_enabled=False)
        self.assertStatus(self.delete(self.st_c1), 204)

    def test_deleting_removes_only_that_comment(self):
        keep = self.add_comment(self.post["id"], self.st_c2)
        self.assertStatus(self.delete(self.st_c1), 204)
        self.assertEqual(list(Comment.objects.values_list("pk", flat=True)), [Comment.objects.get(pk=keep["id"]).pk])


# --------------------------------------------------------------------------- #
# Reactions                                                                    #
# --------------------------------------------------------------------------- #


class ReactionTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.post = self.make_post(self.educator, node=self.d1)

    def reactions(self, response):
        self.assertStatus(response, 200)
        return response.json()["reactions"]

    def test_none_by_default(self):
        self.assertEqual(self.post["reactions"], [])
        self.assertEqual(self.post["commentCount"], 0)
        self.assertEqual(self.detail(self.post["id"], self.st_c1)["reactions"], [])

    def test_put_adds_and_is_idempotent(self):
        expected = [{"kind": "like", "count": 1, "mine": True}]
        self.assertEqual(self.reactions(self.react(self.post["id"], "like", self.st_c1)), expected)
        self.assertEqual(self.reactions(self.react(self.post["id"], "like", self.st_c1)), expected)
        self.assertEqual(Reaction.objects.count(), 1)

    def test_several_kinds_per_user(self):
        self.react(self.post["id"], "love", self.st_c1)
        result = self.reactions(self.react(self.post["id"], "like", self.st_c1))
        self.assertEqual(result, [{"kind": "like", "count": 1, "mine": True}, {"kind": "love", "count": 1, "mine": True}])

    def test_delete_removes_and_is_idempotent(self):
        self.react(self.post["id"], "like", self.st_c1)
        self.react(self.post["id"], "thanks", self.st_c1)
        self.assertEqual(self.reactions(self.unreact(self.post["id"], "like", self.st_c1)),
                         [{"kind": "thanks", "count": 1, "mine": True}])
        self.assertEqual(self.reactions(self.unreact(self.post["id"], "like", self.st_c1)),
                         [{"kind": "thanks", "count": 1, "mine": True}])
        # Never reacted at all: still fine.
        self.assertEqual(self.reactions(self.unreact(self.post["id"], "curious", self.st_c2)),
                         [{"kind": "thanks", "count": 1, "mine": False}])
        self.assertEqual(self.reactions(self.unreact(self.post["id"], "thanks", self.st_c1)), [])
        self.assertFalse(Reaction.objects.exists())

    def test_delete_only_removes_the_callers_reaction(self):
        self.react(self.post["id"], "like", self.st_c1)
        self.react(self.post["id"], "like", self.st_c2)
        self.assertEqual(self.reactions(self.unreact(self.post["id"], "like", self.st_c1)),
                         [{"kind": "like", "count": 1, "mine": False}])
        self.assertTrue(Reaction.objects.filter(user=self.st_c2).exists())

    def test_unknown_kind_is_400(self):
        for kind in ("dislike", "LIKE", "Like", "like ", "x" * 50):
            with self.subTest(kind=kind):
                self.assertStatus(self.react(self.post["id"], kind, self.st_c1), 400)
                self.assertStatus(self.unreact(self.post["id"], kind, self.st_c1), 400)
        self.assertFalse(Reaction.objects.exists())
        self.assertFalse(PostRead.objects.exists())

    def test_unknown_kind_on_hidden_post_is_404(self):
        self.assertStatus(self.react(self.post["id"], "dislike", self.st_c5), 404)

    def test_every_kind_accepted(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assertStatus(self.react(self.post["id"], kind, self.st_c1), 200)
        self.assertEqual(Reaction.objects.count(), len(KINDS))

    def test_counts_aggregate_and_mine_is_per_viewer(self):
        self.react(self.post["id"], "like", self.st_c1)
        self.react(self.post["id"], "like", self.st_c3)
        self.react(self.post["id"], "like", self.admin)
        self.react(self.post["id"], "insightful", self.st_c3)
        for viewer, like_mine, insightful_mine in [
            (self.st_c1, True, False),
            (self.st_c3, True, True),
            (self.admin, True, False),
            (self.st_c2, False, False),
            (self.educator, False, False),
        ]:
            with self.subTest(viewer=viewer.name):
                expected = [
                    {"kind": "like", "count": 3, "mine": like_mine},
                    {"kind": "insightful", "count": 1, "mine": insightful_mine},
                ]
                self.assertEqual(self.detail(self.post["id"], viewer)["reactions"], expected)
                self.assertEqual(self.listed(self.post["id"], viewer)["reactions"], expected)

    def test_order_follows_kinds_and_zero_counts_omitted(self):
        # Added in reverse order; returned in Reaction.KINDS order.
        for kind in reversed(KINDS):
            self.react(self.post["id"], kind, self.st_c1)
        self.assertEqual([r["kind"] for r in self.detail(self.post["id"], self.st_c1)["reactions"]], KINDS)
        self.unreact(self.post["id"], "celebrate", self.st_c1)
        self.unreact(self.post["id"], "like", self.st_c1)
        result = self.reactions(self.react(self.post["id"], "thanks", self.st_c2))
        self.assertEqual([r["kind"] for r in result], ["love", "insightful", "curious", "thanks"])
        self.assertEqual(result[-1], {"kind": "thanks", "count": 2, "mine": True})

    def test_reactions_are_per_post(self):
        other = self.make_post(self.educator, node=self.d1, title="Other")
        self.react(self.post["id"], "like", self.st_c1)
        self.assertEqual(self.reactions(self.react(other["id"], "love", self.st_c1)),
                         [{"kind": "love", "count": 1, "mine": True}])
        self.assertEqual(self.listed(self.post["id"], self.st_c1)["reactions"],
                         [{"kind": "like", "count": 1, "mine": True}])

    def test_student_reaction_marks_post_read(self):
        self.assertEqual(self.unread(self.st_c1), 1)
        self.react(self.post["id"], "like", self.st_c1)
        self.assertEqual(self.unread(self.st_c1), 0)
        self.assertIs(self.detail(self.post["id"], self.st_c1)["read"], True)
        self.assertEqual(self.unread(self.st_c2), 1)

    def test_staff_reaction_creates_no_read(self):
        for user in (self.admin, self.educator, self.other_educator):
            self.react(self.post["id"], "like", user)
        self.assertFalse(PostRead.objects.exists())

    def test_removing_a_reaction_does_not_mark_read(self):
        self.unreact(self.post["id"], "like", self.st_c1)
        self.assertEqual(self.unread(self.st_c1), 1)

    def test_reaction_put_ignores_body(self):
        response = self.request("PUT", reaction_url(self.post["id"], "like"), user=self.st_c1, raw="garbage")
        self.assertStatus(response, 200)


# --------------------------------------------------------------------------- #
# commentsEnabled on posts                                                     #
# --------------------------------------------------------------------------- #


class CommentsEnabledTests(SocialTestCase):
    def patch(self, post_id, body, user=None):
        return self.api_patch(post_url(post_id), body, user=user or self.educator)

    def test_default_true(self):
        post = self.make_post()
        self.assertIs(post["commentsEnabled"], True)
        self.assertIs(Post.objects.get(pk=post["id"]).comments_enabled, True)
        self.assertIs(self.detail(post["id"], self.st_c1)["commentsEnabled"], True)

    def test_post_saved_before_comments_existed_allows_comments(self):
        # A post written before migration 0002 has no comments_enabled at all.
        post = self.make_post()
        connection.database["board_post"].update_one(
            {"_id": ObjectId(post["id"])}, {"$unset": {"comments_enabled": ""}}
        )
        self.assertIsNone(Post.objects.get(pk=post["id"]).comments_enabled)
        self.assertIs(self.detail(post["id"], self.st_c1)["commentsEnabled"], True)
        self.assertStatus(self.comment(post["id"], self.st_c1), 201)
        self.assertStatus(self.comment(post["id"], self.educator), 201)

    def test_multipart_false_disables_on_create(self):
        post = self.make_post(commentsEnabled="false")
        self.assertIs(post["commentsEnabled"], False)
        self.assertIs(Post.objects.get(pk=post["id"]).comments_enabled, False)
        self.assertIs(self.listed(post["id"], self.st_c1)["commentsEnabled"], False)
        self.assertStatus(self.comment(post["id"], self.st_c1), 403)

    def test_other_multipart_values_leave_comments_on(self):
        for value in ("true", "", "no", "False", "0"):
            with self.subTest(value=value):
                self.assertIs(self.make_post(commentsEnabled=value)["commentsEnabled"], True)

    def test_patch_toggles_without_setting_edited_at(self):
        post = self.make_post()
        response = self.patch(post["id"], {"commentsEnabled": False})
        self.assertStatus(response, 200)
        self.assertIs(response.json()["post"]["commentsEnabled"], False)
        self.assertIsNone(response.json()["post"]["editedAt"])
        self.assertIsNone(Post.objects.get(pk=post["id"]).edited_at)
        self.assertStatus(self.comment(post["id"], self.st_c1), 403)

        response = self.patch(post["id"], {"commentsEnabled": True})
        self.assertStatus(response, 200)
        self.assertIs(response.json()["post"]["commentsEnabled"], True)
        self.assertIsNone(Post.objects.get(pk=post["id"]).edited_at)
        self.assertStatus(self.comment(post["id"], self.st_c1), 201)

    def test_patch_with_title_still_sets_edited_at(self):
        post = self.make_post()
        response = self.patch(post["id"], {"commentsEnabled": False, "title": "New"})
        self.assertStatus(response, 200)
        stored = Post.objects.get(pk=post["id"])
        self.assertIsNotNone(stored.edited_at)
        self.assertEqual((stored.title, stored.comments_enabled), ("New", False))

    def test_patch_validation(self):
        post = self.make_post()
        for value in ("false", 0, 1, None, [], {}):
            with self.subTest(value=value):
                self.assertFieldErrors(self.patch(post["id"], {"commentsEnabled": value}), "commentsEnabled")
        self.assertFieldErrors(self.patch(post["id"], {"commentsEnabled": "no", "title": ""}),
                               "commentsEnabled", "title")
        self.assertIs(Post.objects.get(pk=post["id"]).comments_enabled, True)

    def test_only_author_or_admin_can_toggle(self):
        post = self.make_post(self.educator, node=self.c1)
        self.assertStatus(self.patch(post["id"], {"commentsEnabled": False}, self.other_educator), 403)
        self.assertStatus(self.patch(post["id"], {"commentsEnabled": False}, self.st_c1), 403)
        self.assertStatus(self.patch(post["id"], {"commentsEnabled": False}, self.st_c3), 404)
        self.assertStatus(self.patch(post["id"], {"commentsEnabled": False}, self.other_admin), 404)
        self.assertIs(Post.objects.get(pk=post["id"]).comments_enabled, True)
        self.assertStatus(self.patch(post["id"], {"commentsEnabled": False}, self.admin), 200)
        self.assertIs(Post.objects.get(pk=post["id"]).comments_enabled, False)
        self.assertStatus(self.patch(post["id"], {"commentsEnabled": True}, self.educator), 200)
        self.assertIs(Post.objects.get(pk=post["id"]).comments_enabled, True)

    def test_disabling_keeps_existing_comments(self):
        post = self.make_post()
        self.add_comment(post["id"], self.st_c1)
        self.patch(post["id"], {"commentsEnabled": False})
        self.assertEqual(self.detail(post["id"], self.st_c1)["commentCount"], 1)
        self.assertEqual(self.list_comments(post["id"], self.st_c1)["total"], 1)


# --------------------------------------------------------------------------- #
# Deleting posts                                                               #
# --------------------------------------------------------------------------- #


class DeletePostSocialTests(SocialTestCase):
    def test_deleting_a_post_removes_its_comments_and_reactions(self):
        post = self.make_post(self.educator, node=self.s1)
        keep = self.make_post(self.educator, node=self.s1, title="Keep")
        for target in (post, keep):
            self.add_comment(target["id"], self.st_c1)
            self.add_comment(target["id"], self.admin)
            self.react(target["id"], "like", self.st_c1)
            self.react(target["id"], "love", self.st_c2)
        self.assertStatus(self.api_delete(post_url(post["id"]), user=self.educator), 204)
        keep_pk = Post.objects.get(pk=keep["id"]).pk
        self.assertEqual(set(Comment.objects.values_list("post_id", flat=True)), {keep_pk})
        self.assertEqual(set(Reaction.objects.values_list("post_id", flat=True)), {keep_pk})
        self.assertEqual(Comment.objects.count(), 2)
        self.assertEqual(Reaction.objects.count(), 2)
        self.assertStatus(self.api_get(comments_url(post["id"]), user=self.admin), 404)
