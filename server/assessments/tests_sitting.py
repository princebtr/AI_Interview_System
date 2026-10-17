"""Scheduled tests: creation, isolation, sitting, grading and results."""
import json
from datetime import timedelta

from django.utils import timezone

from accounts.auth import create_token
from accounts.tests import ApiTestCase, make_cohort, make_institution, make_user
from assessments.models import Assessment, AssessmentAttempt, Question
from institutions.models import AuditLog

ASSESSMENTS = "/api/assessments"
MY_TESTS = "/api/me/tests"


def make_question(institution, n, correct="B"):
    return Question.objects.create(
        institution=institution,
        subject="Java",
        subject_key="java",
        difficulty="easy",
        text=f"Question {n}?",
        options={"A": "a", "B": "b", "C": "c", "D": "d"},
        correct_answer=correct,
        explanation=f"Because {correct}.",
    )


class SittingTestCase(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.cohort = make_cohort(self.institution, "CSE-2027")
        self.educator = make_user(self.institution, "educator")
        self.student = make_user(self.institution, "student", cohort=self.cohort)
        self.questions = [make_question(self.institution, n) for n in range(1, 5)]

    def auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {create_token(user)}"}

    def payload(self, **overrides):
        body = {
            "title": "Java Fundamentals",
            "cohortId": str(self.cohort.pk),
            "startsAt": (timezone.now() + timedelta(hours=1)).isoformat(),
            "durationMinutes": 30,
            "marksPerQuestion": 2,
            "numQuestions": 4,
            "questionIds": [str(q.pk) for q in self.questions],
        }
        body.update(overrides)
        return body

    def schedule(self, starts_in=timedelta(minutes=-5), duration=30, shuffle=False):
        """Create a test directly (bypassing the 'not in the past' rule) relative to now."""
        return Assessment.objects.create(
            institution=self.institution,
            created_by=self.educator,
            cohort=self.cohort,
            title="Live test",
            starts_at=timezone.now() + starts_in,
            duration_minutes=duration,
            marks_per_question=2,
            shuffle_questions=shuffle,
            questions=[
                {"id": str(q.pk), "text": q.text, "options": q.options, "correctAnswer": "B", "explanation": "b"}
                for q in self.questions
            ],
        )

    def put_answers(self, test, answers, review=None, user=None):
        return self.client.put(
            f"{MY_TESTS}/{test.pk}/answers",
            json.dumps({"answers": answers, "review": review or []}),
            content_type="application/json",
            **self.auth(user or self.student),
        )


class CreateTests(SittingTestCase):
    def test_educator_schedules_a_test_from_the_bank(self):
        response = self.api_post(ASSESSMENTS, self.payload(), user=self.educator)
        self.assertStatus(response, 201)
        body = response.json()["assessment"]
        self.assertEqual((body["questionCount"], body["totalMarks"], body["status"]), (4, 8, "scheduled"))
        test = Assessment.objects.get()
        self.assertEqual(test.questions[0]["correctAnswer"], "B")
        self.assertTrue(AuditLog.objects.filter(action="assessment.created").exists())

        # The snapshot doesn't change when the bank does.
        Question.objects.all().delete()
        test.refresh_from_db()
        self.assertEqual(test.question_count, 4)

    def test_validation(self):
        other = make_institution()
        foreign_cohort = make_cohort(other)
        foreign_question = make_question(other, 99)
        cases = {
            "title": {"title": "ab"},
            "cohortId": {"cohortId": str(foreign_cohort.pk)},
            "startsAt": {"startsAt": (timezone.now() - timedelta(hours=1)).isoformat()},
            "durationMinutes": {"durationMinutes": 2},
            "marksPerQuestion": {"marksPerQuestion": 0},
            "numQuestions": {"numQuestions": 3},
        }
        for field, change in cases.items():
            with self.subTest(field=field):
                self.assertFieldErrors(self.api_post(ASSESSMENTS, self.payload(**change), user=self.educator), field)
        response = self.api_post(
            ASSESSMENTS,
            self.payload(numQuestions=1, questionIds=[str(foreign_question.pk)]),
            user=self.educator,
        )
        self.assertFieldErrors(response, "questionIds")
        self.assertFalse(Assessment.objects.exists())

    def test_naive_start_times_are_rejected(self):
        naive = (timezone.now() + timedelta(hours=1)).replace(tzinfo=None).isoformat()
        self.assertFieldErrors(self.api_post(ASSESSMENTS, self.payload(startsAt=naive), user=self.educator), "startsAt")

    def test_students_cannot_create_or_list_tests(self):
        self.assertStatus(self.api_post(ASSESSMENTS, self.payload(), user=self.student), 403)
        self.assertStatus(self.api_get(ASSESSMENTS, user=self.student), 403)

    def test_educators_see_their_own_tests_and_admins_see_all(self):
        self.api_post(ASSESSMENTS, self.payload(), user=self.educator)
        colleague = make_user(self.institution, "educator")
        admin = make_user(self.institution, "admin")
        self.assertEqual(len(self.api_get(ASSESSMENTS, user=self.educator).json()["assessments"]), 1)
        self.assertEqual(len(self.api_get(ASSESSMENTS, user=colleague).json()["assessments"]), 0)
        self.assertEqual(len(self.api_get(ASSESSMENTS, user=admin).json()["assessments"]), 1)


class SittingTests(SittingTestCase):
    def test_students_only_see_their_cohorts_tests(self):
        test = self.schedule()
        outsider = make_user(self.institution, "student", cohort=make_cohort(self.institution))
        self.assertEqual(len(self.api_get(MY_TESTS, user=self.student).json()["tests"]), 1)
        self.assertEqual(self.api_get(MY_TESTS, user=outsider).json()["tests"], [])
        self.assertStatus(self.api_get(f"{MY_TESTS}/{test.pk}", user=outsider), 404)
        self.assertStatus(self.api_post(f"{MY_TESTS}/{test.pk}/start", user=outsider), 404)

    def test_cannot_start_before_it_opens(self):
        test = self.schedule(starts_in=timedelta(hours=1))
        self.assertStatus(self.api_post(f"{MY_TESTS}/{test.pk}/start", user=self.student), 400)

    def test_full_sitting_hides_answers_until_the_close(self):
        test = self.schedule()
        started = self.api_post(f"{MY_TESTS}/{test.pk}/start", user=self.student)
        self.assertStatus(started, 200)
        attempt = started.json()["attempt"]
        self.assertEqual(attempt["status"], "in_progress")
        self.assertEqual(len(attempt["questions"]), 4)
        self.assertNotIn("correctAnswer", started.content.decode())

        # Starting again resumes the same attempt.
        again = self.api_post(f"{MY_TESTS}/{test.pk}/start", user=self.student)
        self.assertEqual(AssessmentAttempt.objects.count(), 1)
        self.assertEqual(again.json()["attempt"]["questions"], attempt["questions"])

        ids = [q["id"] for q in attempt["questions"]]
        self.assertStatus(self.put_answers(test, {ids[0]: "B", ids[1]: "A"}, review=[ids[2]]), 200)
        self.assertStatus(self.put_answers(test, {"not-a-question": "B"}), 400)
        self.assertStatus(self.put_answers(test, {ids[0]: "E"}), 400)

        submitted = self.api_post(
            f"{MY_TESTS}/{test.pk}/submit", {"answers": {ids[0]: "B", ids[1]: "A", ids[2]: "B"}}, user=self.student
        )
        self.assertStatus(submitted, 200)
        result = submitted.json()["attempt"]
        self.assertEqual((result["status"], result["correct"], result["score"], result["percentage"]), ("submitted", 2, 4, 50.0))
        self.assertNotIn("review", result)  # still open for others: no answers yet
        self.assertNotIn("correctAnswer", submitted.content.decode())
        self.assertStatus(self.put_answers(test, {ids[0]: "C"}), 400)

        # After the close, the review with correct answers appears.
        Assessment.objects.filter(pk=test.pk).update(starts_at=timezone.now() - timedelta(hours=2))
        review = self.api_get(f"{MY_TESTS}/{test.pk}", user=self.student).json()["attempt"]["review"]
        self.assertEqual({r["correctAnswer"] for r in review}, {"B"})
        self.assertEqual(sum(r["yourAnswer"] == "B" for r in review), 2)

    def test_open_attempts_are_submitted_automatically_at_the_close(self):
        test = self.schedule()
        ids = [q["id"] for q in self.api_post(f"{MY_TESTS}/{test.pk}/start", user=self.student).json()["attempt"]["questions"]]
        self.put_answers(test, {ids[0]: "B", ids[1]: "B", ids[2]: "B"})
        Assessment.objects.filter(pk=test.pk).update(starts_at=timezone.now() - timedelta(hours=2))

        mine = self.api_get(MY_TESTS, user=self.student).json()["tests"][0]["attempt"]
        self.assertEqual((mine["status"], mine["correct"], mine["score"], mine["autoSubmitted"]), ("submitted", 3, 6, True))
        attempt = AssessmentAttempt.objects.get()
        self.assertTrue(attempt.auto_submitted)
        self.assertEqual(attempt.submitted_at, Assessment.objects.get().ends_at)

    def test_submission_in_the_grace_period_counts_as_automatic(self):
        # The browser submits when its timer hits zero; the request lands just after the close.
        test = self.schedule()
        ids = [q["id"] for q in self.api_post(f"{MY_TESTS}/{test.pk}/start", user=self.student).json()["attempt"]["questions"]]
        Assessment.objects.filter(pk=test.pk).update(starts_at=timezone.now() - timedelta(minutes=30, seconds=5))
        response = self.api_post(f"{MY_TESTS}/{test.pk}/submit", {"answers": {ids[0]: "B"}}, user=self.student)
        result = response.json()["attempt"]
        self.assertEqual((result["correct"], result["autoSubmitted"]), (1, True))  # answers still accepted
        self.assertIn("review", result)  # closed, so the answer key is shown
        self.assertEqual(AssessmentAttempt.objects.get().submitted_at, Assessment.objects.get().ends_at)

    def test_late_submissions_cannot_change_answers(self):
        test = self.schedule()
        ids = [q["id"] for q in self.api_post(f"{MY_TESTS}/{test.pk}/start", user=self.student).json()["attempt"]["questions"]]
        self.put_answers(test, {ids[0]: "A"})
        Assessment.objects.filter(pk=test.pk).update(starts_at=timezone.now() - timedelta(minutes=31))
        response = self.api_post(
            f"{MY_TESTS}/{test.pk}/submit", {"answers": {i: "B" for i in ids}}, user=self.student
        )
        self.assertEqual(response.json()["attempt"]["correct"], 0)

    def test_missing_a_closed_test(self):
        test = self.schedule(starts_in=timedelta(hours=-2))
        mine = self.api_get(MY_TESTS, user=self.student).json()["tests"][0]["attempt"]
        self.assertEqual(mine["status"], "missed")
        self.assertStatus(self.api_post(f"{MY_TESTS}/{test.pk}/start", user=self.student), 400)


class ResultsTests(SittingTestCase):
    def test_educator_sees_every_students_status(self):
        test = self.schedule()
        waiting = make_user(self.institution, "student", cohort=self.cohort, name="Not Started")
        ids = [q["id"] for q in self.api_post(f"{MY_TESTS}/{test.pk}/start", user=self.student).json()["attempt"]["questions"]]
        self.api_post(f"{MY_TESTS}/{test.pk}/submit", {"answers": {i: "B" for i in ids}}, user=self.student)

        body = self.api_get(f"{ASSESSMENTS}/{test.pk}", user=self.educator).json()
        statuses = {r["student"]["id"]: r["status"] for r in body["results"]}
        self.assertEqual(statuses[str(self.student.pk)], "submitted")
        self.assertEqual(statuses[str(waiting.pk)], "not_started")
        self.assertEqual(body["stats"]["averagePercentage"], 100.0)
        self.assertEqual(body["assessment"]["questions"][0]["correctAnswer"], "B")

    def test_other_educators_cannot_see_results(self):
        test = self.schedule()
        colleague = make_user(self.institution, "educator")
        self.assertStatus(self.api_get(f"{ASSESSMENTS}/{test.pk}", user=colleague), 404)
        stranger = make_user(make_institution(), "admin")
        self.assertStatus(self.api_get(f"{ASSESSMENTS}/{test.pk}", user=stranger), 404)

    def test_tests_can_be_deleted_only_before_anyone_starts(self):
        test = self.schedule()
        self.api_post(f"{MY_TESTS}/{test.pk}/start", user=self.student)
        self.assertStatus(self.client.delete(f"{ASSESSMENTS}/{test.pk}", **self.auth(self.educator)), 400)

        unstarted = self.schedule(starts_in=timedelta(hours=1))
        self.assertStatus(self.client.delete(f"{ASSESSMENTS}/{unstarted.pk}", **self.auth(self.educator)), 204)

    def test_cohorts_with_tests_cannot_be_deleted(self):
        empty = make_cohort(self.institution, "Empty")
        Assessment.objects.create(
            institution=self.institution, created_by=self.educator, cohort=empty, title="T",
            starts_at=timezone.now() + timedelta(days=1), duration_minutes=30, marks_per_question=1,
            questions=[],
        )
        admin = make_user(self.institution, "admin")
        self.assertStatus(self.client.delete(f"/api/institution/cohorts/{empty.pk}", **self.auth(admin)), 400)
