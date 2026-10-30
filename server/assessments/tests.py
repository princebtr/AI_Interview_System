"""Question bank and educator workspace endpoints."""
from accounts.tests import (
    ApiTestCase,
    make_cohort,
    make_department,
    make_institution,
    make_section,
    make_user,
)
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

    def test_overview_reports_bank_sections_and_subjects(self):
        empty_section = make_section(self.cohort.section.department, "Z")
        body = self.api_get(OVERVIEW, user=self.educator).json()
        self.assertEqual(body["counts"]["students"], 1)
        self.assertEqual(
            {k: body["counts"][k] for k in ("batches", "departments", "sections", "cohorts")},
            {"batches": 1, "departments": 1, "sections": 2, "cohorts": 1},
        )
        self.assertNotIn("cohorts", body)
        self.assertEqual(body["practice"]["last7Days"], 1)
        section = self.cohort.section
        department = section.department
        self.assertEqual(
            body["sections"],
            [
                {
                    "id": str(section.pk),
                    "name": section.name,
                    "label": f"{department.batch.name} · {department.name} · {section.name}",
                    "attempts": 1,
                    "averageScore": 80.0,
                    "students": 1,
                },
                {
                    "id": str(empty_section.pk),
                    "name": "Z",
                    "label": f"{department.batch.name} · {department.name} · Z",
                    "attempts": 0,
                    "averageScore": None,
                    "students": 0,
                },
            ],
        )
        self.assertEqual(body["subjects"], [{"subject": "Java", "attempts": 1, "averageScore": 80.0}])

    def test_students_list_includes_practice_stats(self):
        body = self.api_get(STUDENTS, user=self.educator).json()
        self.assertEqual(body["total"], 1)
        row = body["students"][0]
        self.assertEqual((row["name"], row["attempts"], row["averageScore"]), ("Asha Rao", 1, 80.0))
        self.assertEqual(row["cohort"]["name"], "CSE-2027")
        self.assertEqual(row["placement"]["cohort"]["name"], "CSE-2027")
        self.assertEqual(row["placement"]["label"], self.cohort.label)

    def test_students_can_be_filtered_by_any_level(self):
        section = self.cohort.section
        department = section.department
        batch = department.batch
        lab_mate = make_user(self.institution, "student", cohort=make_cohort(self.institution, section=section))
        section_b = make_user(
            self.institution, "student", cohort=make_cohort(self.institution, section=make_section(department, "B"))
        )
        ece = make_user(
            self.institution, "student",
            cohort=make_cohort(self.institution, section=make_section(make_department(batch, "ECE"))),
        )
        elsewhere = make_user(self.institution, "student", cohort=make_cohort(self.institution))
        cases = [
            ({}, {self.student, lab_mate, section_b, ece, elsewhere}),
            ({"batch": str(batch.pk)}, {self.student, lab_mate, section_b, ece}),
            ({"department": str(department.pk)}, {self.student, lab_mate, section_b}),
            ({"section": str(section.pk)}, {self.student, lab_mate}),
            ({"cohort": str(self.cohort.pk)}, {self.student}),
            ({"batch": str(batch.pk), "section": str(section_b.section_id)}, {section_b}),
            ({"department": str(ece.department_id), "cohort": str(self.cohort.pk)}, set()),
        ]
        for params, expected in cases:
            with self.subTest(params=params):
                response = self.api_get(STUDENTS, params, user=self.educator)
                self.assertStatus(response, 200)
                self.assertEqual({s["id"] for s in response.json()["students"]}, {str(u.pk) for u in expected})
                self.assertEqual(response.json()["total"], len(expected))

    def test_unknown_or_foreign_groups_are_rejected(self):
        other = make_institution()
        foreign = make_cohort(other)
        foreign_ids = {
            "batch": foreign.section.department.batch_id,
            "department": foreign.section.department_id,
            "section": foreign.section_id,
            "cohort": foreign.pk,
        }
        for level, foreign_id in foreign_ids.items():
            for value in (str(foreign_id), "nope", str(self.cohort.pk) if level != "cohort" else "("):
                with self.subTest(level=level, value=value):
                    response = self.api_get(STUDENTS, {level: value}, user=self.educator)
                    self.assertStatus(response, 400)
                    self.assertEqual(response.json()["message"], f"Unknown {level}")
                    self.assertNotIn("students", response.json())

    def test_students_cannot_see_teaching_data(self):
        self.assertStatus(self.api_get(OVERVIEW, user=self.student), 403)
        self.assertStatus(self.api_get(STUDENTS, user=self.student), 403)
