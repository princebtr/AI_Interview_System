"""Question analysis on a test's results, and reusing a test's questions."""
from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from accounts.tests import make_user
from assessments.assessment_views import question_stats
from assessments.models import AssessmentAttempt
from assessments.tests_sitting import ASSESSMENTS, SittingTestCase, make_question

Q = {"id": "q1", "options": {"A": "a", "B": "b", "C": "c", "D": "d"}, "correctAnswer": "B"}


class Sub:
    def __init__(self, answers):
        self.answers = answers


def stats_for(*letters):
    """Stats for question q1 from one submitted attempt per letter (None: skipped)."""
    return question_stats([Q], [Sub({} if letter is None else {"q1": letter}) for letter in letters])["q1"]


class QuestionStatsTests(SimpleTestCase):
    def test_counts(self):
        st = stats_for("B", "B", "A", None)
        self.assertEqual((st["answered"], st["skipped"], st["correct"]), (3, 1, 2))
        self.assertEqual(st["picks"], {"A": 1, "B": 2, "C": 0, "D": 0})
        self.assertAlmostEqual(st["percentCorrect"], 66.7)
        self.assertIsNone(st["flag"])  # too few answers to judge

    def test_flags(self):
        self.assertEqual(stats_for(*"BBBBBBBBBB")["flag"], "too_easy")
        self.assertEqual(stats_for(*"BBBAAACCDD")["flag"], "too_hard")  # 30%, no wrong option ahead
        self.assertEqual(stats_for(*"CCCCBBBA")["flag"], "check_key")  # a wrong option beats the key
        self.assertIsNone(stats_for(*"BBBBBBAACD")["flag"])  # 60%: fine

    def test_no_answers(self):
        st = stats_for()
        self.assertEqual((st["answered"], st["percentCorrect"], st["flag"]), (0, None, None))

    def test_ignores_letters_that_arent_options(self):
        self.assertEqual(stats_for("Z", "B")["answered"], 1)


class TestPageTests(SittingTestCase):
    def test_results_include_question_stats_from_submitted_attempts_only(self):
        test = self.schedule()
        q1, q2 = test.questions[0]["id"], test.questions[1]["id"]
        others = [make_user(self.institution, "student", cohort=self.cohort) for _ in range(2)]
        done = timezone.now()
        AssessmentAttempt.objects.create(
            assessment=test, student=self.student, order=[], answers={q1: "B", q2: "A"}, submitted_at=done, correct=1
        )
        AssessmentAttempt.objects.create(
            assessment=test, student=others[0], order=[], answers={q1: "C"}, submitted_at=done, correct=0
        )
        AssessmentAttempt.objects.create(assessment=test, student=others[1], order=[], answers={q1: "D"})  # still open

        response = self.api_get(f"{ASSESSMENTS}/{test.pk}", user=self.educator)
        self.assertStatus(response, 200)
        body = response.json()
        stats = body["questionStats"]
        self.assertEqual(stats[q1]["picks"], {"A": 0, "B": 1, "C": 1, "D": 0})
        self.assertEqual((stats[q2]["answered"], stats[q2]["skipped"]), (1, 1))
        self.assertEqual(set(stats), {q["id"] for q in test.questions})

    def test_question_bank_by_ids_for_duplicating(self):
        wanted = [str(self.questions[0].pk), str(self.questions[2].pk)]
        response = self.api_get("/api/questions", {"ids": ",".join(wanted + ["not-an-id"])}, user=self.educator)
        self.assertStatus(response, 200)
        self.assertEqual({q["id"] for q in response.json()["questions"]}, set(wanted))

        # Another institution's question isn't found by id.
        from accounts.tests import make_institution

        foreign = make_question(make_institution(), 9)
        response = self.api_get("/api/questions", {"ids": str(foreign.pk)}, user=self.educator)
        self.assertEqual(response.json()["questions"], [])

    def test_duplicate_reuses_the_settings(self):
        """What the Duplicate button sends: the source test's settings with a new start."""
        source = self.api_post(ASSESSMENTS, self.payload(shuffleQuestions=False), user=self.educator).json()["assessment"]
        detail = self.api_get(f"{ASSESSMENTS}/{source['id']}", user=self.educator).json()["assessment"]
        copy = self.api_post(
            ASSESSMENTS,
            self.payload(
                title=f"{detail['title']} (copy)",
                startsAt=(timezone.now() + timedelta(days=7)).isoformat(),
                questionIds=[q["id"] for q in detail["questions"]],
                shuffleQuestions=detail["shuffleQuestions"],
            ),
            user=self.educator,
        )
        self.assertStatus(copy, 201)
        self.assertEqual(copy.json()["assessment"]["title"], "Java Fundamentals (copy)")
