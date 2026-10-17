"""Question bank and educator workspace endpoints."""
from accounts.tests import ApiTestCase, make_cohort, make_institution, make_user
from ai.models import PracticeAttempt
from assessments.models import Question

QUESTIONS = "/api/questions"
OVERVIEW = "/api/teaching/overview"
STUDENTS = "/api/teaching/students"


def question(**overrides):
    item = {
        "text": "What is 2 + 2?",
        "options": {"A": "3", "B": "4", "C": "5", "D": "22"},
        "correctAnswer": "B",
        "subject": "Maths",
        "difficulty": "easy",
        "aiGenerated": True,
        "explanation": "Arithmetic.",
    }
    item.update(overrides)
    return item


class QuestionBankTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.educator = make_user(self.institution, "educator")
        self.student = make_user(self.institution, "student", cohort=make_cohort(self.institution))

    def save(self, *items, user=None):
        return self.api_post(QUESTIONS, {"questions": list(items)}, user=user or self.educator)

    def test_educator_saves_and_lists_questions(self):
        response = self.save(question(), question(text="Capital of France?", subject="Geography",
                                                  options={"A": "Paris", "B": "Rome", "C": "Oslo", "D": "Bern"},
                                                  correctAnswer="A"))
        self.assertStatus(response, 201)
        self.assertEqual(response.json()["created"], 2)
        body = self.api_get(QUESTIONS, user=self.educator).json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["subjects"], ["Geography", "Maths"])
        self.assertEqual(body["questions"][0]["createdBy"]["id"], str(self.educator.pk))
        filtered = self.api_get(QUESTIONS, {"subject": "maths"}, user=self.educator).json()
        self.assertEqual(filtered["total"], 1)

    def test_invalid_questions_are_rejected_without_saving_any(self):
        response = self.save(question(), question(correctAnswer="E"), question(options={"A": "x"}))
        self.assertStatus(response, 400)
        self.assertFalse(Question.objects.exists())

    def test_students_cannot_use_the_bank(self):
        self.assertStatus(self.api_get(QUESTIONS, user=self.student), 403)
        self.assertStatus(self.save(question(), user=self.student), 403)

    def test_other_institutions_questions_are_invisible(self):
        self.save(question())
        other = make_user(make_institution(), "educator")
        self.assertEqual(self.api_get(QUESTIONS, user=other).json()["total"], 0)
        qid = Question.objects.get().pk
        self.assertStatus(self.client.delete(f"{QUESTIONS}/{qid}", **self.auth(other)), 404)

    def test_only_the_author_or_an_admin_can_delete(self):
        self.save(question())
        qid = Question.objects.get().pk
        colleague = make_user(self.institution, "educator")
        self.assertStatus(self.client.delete(f"{QUESTIONS}/{qid}", **self.auth(colleague)), 403)
        admin = make_user(self.institution, "admin")
        self.assertStatus(self.client.delete(f"{QUESTIONS}/{qid}", **self.auth(admin)), 204)
        self.assertFalse(Question.objects.exists())

    def auth(self, user):
        from accounts.auth import create_token

        return {"HTTP_AUTHORIZATION": f"Bearer {create_token(user)}"}


class TeachingTests(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.cohort = make_cohort(self.institution, "CSE-2027")
        self.educator = make_user(self.institution, "educator")
        self.student = make_user(self.institution, "student", cohort=self.cohort, name="Asha Rao")
        PracticeAttempt.objects.create(
            institution=self.institution, user=self.student, kind="mcq", subject="Java",
            subject_key="java", score=80,
        )

    def test_overview_reports_bank_cohorts_and_subjects(self):
        body = self.api_get(OVERVIEW, user=self.educator).json()
        self.assertEqual(body["counts"]["students"], 1)
        self.assertEqual(body["practice"]["last7Days"], 1)
        self.assertEqual(body["cohorts"][0]["name"], "CSE-2027")
        self.assertEqual(body["cohorts"][0]["averageScore"], 80.0)
        self.assertEqual(body["subjects"], [{"subject": "Java", "attempts": 1, "averageScore": 80.0}])

    def test_students_list_includes_practice_stats(self):
        body = self.api_get(STUDENTS, user=self.educator).json()
        self.assertEqual(body["total"], 1)
        row = body["students"][0]
        self.assertEqual((row["name"], row["attempts"], row["averageScore"]), ("Asha Rao", 1, 80.0))
        self.assertEqual(row["cohort"]["name"], "CSE-2027")

    def test_students_cannot_see_teaching_data(self):
        self.assertStatus(self.api_get(OVERVIEW, user=self.student), 403)
        self.assertStatus(self.api_get(STUDENTS, user=self.student), 403)
