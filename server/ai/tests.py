"""Practice endpoints: server-side grading, one-time submission, role checks,
recorded attempts and the student performance summary. Gemini is mocked."""
from unittest import mock

from accounts.tests import ApiTestCase, make_cohort, make_institution, make_user
from ai.models import PracticeAttempt, PracticeQuestion, PracticeQuiz

GENERATE_MCQ = "/api/ai/generate-mcq-questions"
EVALUATE_MCQ = "/api/ai/evaluate-mcq-answers"
GENERATE_QUESTION = "/api/ai/generate-question"
EVALUATE_ANSWER = "/api/ai/evaluate-answer"
PERFORMANCE = "/api/me/performance"

QUESTIONS = [
    {
        "id": i,
        "question": f"Question {i}?",
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
        "correctAnswer": "B",
        "explanation": "Because B.",
    }
    for i in (1, 2, 3, 4)
]


class PracticeTestCase(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.cohort = make_cohort(self.institution)
        self.student = make_user(self.institution, "student", cohort=self.cohort)
        self.educator = make_user(self.institution, "educator")

    def generate_quiz(self, user=None, subject="Java"):
        with mock.patch("ai.services.generate_mcq", return_value=[dict(q) for q in QUESTIONS]):
            return self.api_post(GENERATE_MCQ, {"subject": subject, "numQuestions": 4}, user=user or self.student)


class MultipleChoiceTests(PracticeTestCase):
    def test_students_never_receive_answer_keys(self):
        response = self.generate_quiz()
        self.assertStatus(response, 200)
        body = response.json()
        self.assertTrue(body["quizId"])
        for q in body["questions"]:
            self.assertEqual(set(q), {"id", "question", "options"})
        self.assertNotIn('"correctAnswer"', response.content.decode())

    def test_staff_get_answer_keys_to_review_and_nothing_is_stored(self):
        response = self.generate_quiz(user=self.educator)
        self.assertStatus(response, 200)
        self.assertEqual(response.json()["questions"][0]["correctAnswer"], "B")
        self.assertNotIn("quizId", response.json())
        self.assertFalse(PracticeQuiz.objects.exists())

    def test_answers_are_graded_on_the_server_and_recorded(self):
        quiz = self.generate_quiz().json()["quizId"]
        response = self.api_post(
            EVALUATE_MCQ, {"quizId": quiz, "userAnswers": {"1": "B", "2": "b", "3": "A"}}, user=self.student
        )
        self.assertStatus(response, 200)
        body = response.json()
        self.assertEqual((body["score"], body["totalQuestions"], body["percentage"]), (2, 4, 50.0))
        self.assertEqual(body["results"][0]["explanation"], "Because B.")
        attempt = PracticeAttempt.objects.get()
        self.assertEqual((attempt.kind, attempt.subject, attempt.score), ("mcq", "Java", 50.0))
        self.assertEqual((attempt.correct, attempt.total), (2, 4))
        self.assertEqual(attempt.institution_id, self.institution.pk)

    def test_client_supplied_answer_keys_are_ignored(self):
        quiz = self.generate_quiz().json()["quizId"]
        forged = [dict(q, correctAnswer="A") for q in QUESTIONS]
        response = self.api_post(
            EVALUATE_MCQ,
            {"quizId": quiz, "questions": forged, "userAnswers": {"1": "A", "2": "A", "3": "A", "4": "A"}},
            user=self.student,
        )
        self.assertEqual(response.json()["score"], 0)

    def test_a_quiz_can_only_be_submitted_once(self):
        quiz = self.generate_quiz().json()["quizId"]
        answers = {"quizId": quiz, "userAnswers": {"1": "B"}}
        self.assertStatus(self.api_post(EVALUATE_MCQ, answers, user=self.student), 200)
        self.assertStatus(self.api_post(EVALUATE_MCQ, answers, user=self.student), 400)
        self.assertEqual(PracticeAttempt.objects.count(), 1)

    def test_another_students_quiz_cannot_be_submitted(self):
        quiz = self.generate_quiz().json()["quizId"]
        other = make_user(self.institution, "student", cohort=self.cohort)
        response = self.api_post(EVALUATE_MCQ, {"quizId": quiz, "userAnswers": {"1": "B"}}, user=other)
        self.assertStatus(response, 400)
        self.assertFalse(PracticeAttempt.objects.exists())

    def test_malformed_quiz_id_is_400(self):
        response = self.api_post(EVALUATE_MCQ, {"quizId": "nope", "userAnswers": {"1": "B"}}, user=self.student)
        self.assertStatus(response, 400)

    def test_staff_cannot_submit_practice(self):
        self.assertStatus(self.api_post(EVALUATE_MCQ, {"quizId": "x", "userAnswers": {"1": "B"}}, user=self.educator), 403)

    def test_difficulty_must_be_known(self):
        response = self.api_post(
            GENERATE_MCQ, {"subject": "Java", "numQuestions": 4, "difficulty": "extreme"}, user=self.educator
        )
        self.assertStatus(response, 400)


class InterviewTests(PracticeTestCase):
    def ask(self, subject="Java"):
        with mock.patch("ai.services.generate_question", return_value="What is a JVM?"):
            return self.api_post(GENERATE_QUESTION, {"subject": subject}, user=self.student)

    def test_answers_are_scored_once_against_the_stored_question(self):
        question_id = self.ask().json()["questionId"]
        with mock.patch("ai.services.evaluate_answer", return_value=7) as evaluate:
            response = self.api_post(EVALUATE_ANSWER, {"questionId": question_id, "answer": "A VM"}, user=self.student)
            self.assertStatus(response, 200)
            self.assertEqual(response.json()["score"], 7)
            evaluate.assert_called_once_with("What is a JVM?", "A VM")
            again = self.api_post(EVALUATE_ANSWER, {"questionId": question_id, "answer": "Again"}, user=self.student)
            self.assertStatus(again, 400)
        attempt = PracticeAttempt.objects.get()
        self.assertEqual((attempt.kind, attempt.score), ("interview", 70))
        self.assertIsNotNone(PracticeQuestion.objects.get().answered_at)

    def test_interview_practice_is_for_students_only(self):
        for user in (self.educator, make_user(self.institution, "admin")):
            with self.subTest(role=user.role):
                self.assertStatus(self.api_post(GENERATE_QUESTION, {"subject": "Java"}, user=user), 403)


class PerformanceTests(PracticeTestCase):
    def record(self, subject, score, kind="mcq", user=None):
        return PracticeAttempt.objects.create(
            institution=self.institution,
            user=user or self.student,
            kind=kind,
            subject=subject,
            subject_key=PracticeAttempt.key_for(subject),
            score=score,
        )

    def test_empty_summary(self):
        body = self.api_get(PERFORMANCE, user=self.student).json()
        self.assertEqual(body["summary"]["attempts"], 0)
        self.assertIsNone(body["summary"]["overall"])
        self.assertEqual(body["subjects"], [])

    def test_summary_subjects_and_areas_to_improve(self):
        self.record("Java", 90)
        self.record("java ", 70)  # same subject, different spelling
        self.record("DBMS", 50, kind="interview")
        self.record("Java", 10, user=make_user(self.institution, "student", cohort=self.cohort))  # not mine
        body = self.api_get(PERFORMANCE, user=self.student).json()
        summary = body["summary"]
        self.assertEqual((summary["attempts"], summary["assessments"], summary["interviewAnswers"]), (3, 2, 1))
        self.assertEqual(summary["overall"], 70.0)
        self.assertEqual(summary["interviewAverage"], 50.0)
        self.assertEqual(summary["streakDays"], 1)
        subjects = {s["subject"].strip().lower(): s for s in body["subjects"]}
        self.assertEqual(subjects["java"]["attempts"], 2)
        self.assertEqual(subjects["java"]["averageScore"], 80.0)
        self.assertEqual(body["improve"], ["DBMS"])

    def test_staff_have_no_personal_performance(self):
        self.assertStatus(self.api_get(PERFORMANCE, user=self.educator), 403)
