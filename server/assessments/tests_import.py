"""Question CSV import (POST /api/questions/import) and manual "write your own"
questions through POST /api/questions."""
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.auth import create_token
from accounts.tests import ApiTestCase, make_cohort, make_institution, make_user
from assessments.models import Question
from institutions.models import AuditLog

IMPORT = "/api/questions/import"
QUESTIONS = "/api/questions"
SAMPLE = Path(__file__).resolve().parents[2] / "client" / "public" / "sample-questions.csv"

HEADER = "subject,topic,difficulty,question,option_a,option_b,option_c,option_d,correct_answer,explanation\n"


def row(question="What is 2 + 2?", answer="B", subject="Maths", topic="Arithmetic", difficulty="easy",
        options=("3", "4", "5", "22"), explanation="Adding."):
    cells = [subject, topic, difficulty, question, *options, answer, explanation]
    return ",".join(f'"{c}"' if ("," in c or '"' in c or "\n" in c) else c for c in cells) + "\n"


class ImportTestCase(ApiTestCase):
    def setUp(self):
        self.institution = make_institution()
        self.educator = make_user(self.institution, "educator")
        self.admin = make_user(self.institution, "admin")
        self.student = make_user(self.institution, "student", cohort=make_cohort(self.institution))

    def upload(self, content, *, commit=False, subject=None, user=None, name="questions.csv", auth=True):
        if isinstance(content, str):
            content = content.encode("utf-8")
        data = {"file": SimpleUploadedFile(name, content, content_type="text/csv")}
        if commit:
            data["commit"] = "true"
        if subject is not None:
            data["subject"] = subject
        headers = {}
        if auth:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {create_token(user or self.educator)}"
        return self.client.post(IMPORT, data, **headers)

    def preview(self, content, **kwargs):
        response = self.upload(content, **kwargs)
        self.assertStatus(response, 200)
        return response.json()

    def row_errors(self, *rows, header=HEADER, **kwargs):
        """Errors of each previewed row."""
        return [r["errors"] for r in self.preview(header + "".join(rows), **kwargs)["rows"]]

    def assertRejected(self, response, *fragments):
        self.assertStatus(response, 400)
        message = response.json()["message"]
        for fragment in fragments:
            self.assertIn(fragment, message)
        self.assertFalse(Question.objects.exists())
        return message

    def bank(self, **fields):
        item = {
            "institution": self.institution, "created_by": self.educator, "subject": "Maths",
            "subject_key": "maths", "text": "What is 2 + 2?", "options": {"A": "3", "B": "4", "C": "5", "D": "22"},
            "correct_answer": "B",
        }
        item.update(fields)
        return Question.objects.create(**item)


# --------------------------------------------------------------------------- #
# Access, preview and commit                                                  #
# --------------------------------------------------------------------------- #


class ImportAccessTests(ImportTestCase):
    def test_requires_authentication(self):
        self.assertStatus(self.upload(HEADER + row(), commit=True, auth=False), 401)
        self.assertFalse(Question.objects.exists())

    def test_students_are_forbidden(self):
        self.assertStatus(self.upload(HEADER + row(), commit=True, user=self.student), 403)
        self.assertFalse(Question.objects.exists())

    def test_get_is_not_allowed(self):
        response = self.client.get(IMPORT, HTTP_AUTHORIZATION=f"Bearer {create_token(self.educator)}")
        self.assertStatus(response, 405)

    def test_educator_import_belongs_to_caller(self):
        response = self.upload(HEADER + row(), commit=True)
        self.assertStatus(response, 201)
        q = Question.objects.get()
        self.assertEqual(q.institution_id, self.institution.pk)
        self.assertEqual(q.created_by_id, self.educator.pk)
        self.assertIs(q.ai_generated, False)
        self.assertEqual(q.subject_key, "maths")
        self.assertEqual((q.text, q.topic, q.difficulty, q.correct_answer, q.explanation),
                         ("What is 2 + 2?", "Arithmetic", "easy", "B", "Adding."))
        self.assertEqual(q.options, {"A": "3", "B": "4", "C": "5", "D": "22"})

    def test_admin_can_import(self):
        self.assertStatus(self.upload(HEADER + row(), commit=True, user=self.admin), 201)
        q = Question.objects.get()
        self.assertEqual(q.created_by_id, self.admin.pk)
        self.assertEqual(AuditLog.objects.get(action="questions.imported").actor_id, self.admin.pk)

    def test_imported_questions_appear_in_the_bank_list(self):
        self.upload(HEADER + row(), commit=True)
        body = self.api_get(QUESTIONS, user=self.educator).json()
        self.assertEqual(body["total"], 1)
        self.assertIs(body["questions"][0]["aiGenerated"], False)
        other = make_user(make_institution(), "educator")
        self.assertEqual(self.api_get(QUESTIONS, user=other).json()["total"], 0)


class SampleFileTests(ImportTestCase):
    def sample(self):
        return SAMPLE.read_bytes()

    def test_sample_previews_as_six_valid_rows(self):
        body = self.preview(self.sample())
        self.assertEqual(body["summary"], {"total": 6, "valid": 6, "invalid": 0})
        rows = body["rows"]
        self.assertEqual([r["line"] for r in rows], [2, 3, 4, 5, 6, 7])
        self.assertTrue(all(r["errors"] == [] for r in rows))
        # "2NF" resolves to B by option text.
        self.assertEqual(rows[4]["correctAnswer"], "B")
        # Blank difficulty defaults to medium.
        self.assertEqual(rows[5]["difficulty"], "medium")
        # Quoted cells containing commas stay whole.
        self.assertEqual(rows[2]["text"], "In a binary search tree, which traversal visits the keys in sorted order?")
        self.assertEqual(rows[0]["explanation"],
                         "A stack removes the most recently added item first, so the last item in is the first out.")
        self.assertEqual(rows[3]["explanation"], "")
        self.assertFalse(Question.objects.exists())
        self.assertFalse(AuditLog.objects.filter(action="questions.imported").exists())

    def test_sample_imports_six_questions(self):
        response = self.upload(self.sample(), commit=True)
        self.assertStatus(response, 201)
        body = response.json()
        self.assertEqual(body["created"], 6)
        self.assertEqual(body["skipped"], 0)
        self.assertEqual(body["subjects"], ["Data Structures", "DBMS", "Java", "Operating Systems"])
        self.assertEqual(Question.objects.filter(institution=self.institution).count(), 6)
        self.assertEqual(Question.objects.get(subject="DBMS").correct_answer, "B")
        self.assertEqual(Question.objects.get(subject="Operating Systems").difficulty, "medium")
        self.assertFalse(Question.objects.filter(ai_generated=True).exists())

    def test_sample_imported_twice_is_all_duplicates(self):
        self.assertStatus(self.upload(self.sample(), commit=True), 201)
        body = self.preview(self.sample())
        self.assertEqual(body["summary"], {"total": 6, "valid": 0, "invalid": 6})
        self.assertTrue(all(r["errors"] == ["Already in the question bank"] for r in body["rows"]))
        response = self.upload(self.sample(), commit=True)
        self.assertStatus(response, 400)
        self.assertEqual(Question.objects.count(), 6)


class PreviewAndCommitTests(ImportTestCase):
    def test_preview_creates_nothing(self):
        body = self.preview(HEADER + row() + row(question="", answer="A"))
        self.assertEqual(body["summary"], {"total": 2, "valid": 1, "invalid": 1})
        self.assertEqual(body["rows"][0], {
            "line": 2, "text": "What is 2 + 2?", "subject": "Maths", "topic": "Arithmetic", "difficulty": "easy",
            "options": {"A": "3", "B": "4", "C": "5", "D": "22"}, "correctAnswer": "B",
            "explanation": "Adding.", "errors": [],
        })
        self.assertNotIn("_fields", body["rows"][0])
        self.assertFalse(Question.objects.exists())
        self.assertFalse(AuditLog.objects.exists())

    def test_commit_must_be_exactly_true(self):
        response = self.client.post(
            IMPORT, {"file": SimpleUploadedFile("q.csv", (HEADER + row()).encode()), "commit": "yes"},
            HTTP_AUTHORIZATION=f"Bearer {create_token(self.educator)}",
        )
        self.assertStatus(response, 200)
        self.assertFalse(Question.objects.exists())

    def test_commit_creates_only_valid_rows(self):
        content = HEADER + row() + row(question="Bad one", answer="E") + row(question="Capital of France?",
                                                                            subject="Geography",
                                                                            options=("Paris", "Rome", "Oslo", "Bern"),
                                                                            answer="Paris")
        response = self.upload(content, commit=True)
        self.assertStatus(response, 201)
        body = response.json()
        self.assertEqual((body["created"], body["skipped"]), (2, 1))
        self.assertEqual(body["subjects"], ["Geography", "Maths"])
        self.assertEqual(len(body["rows"]), 3)
        self.assertEqual(body["rows"][1]["errors"],
                         ["Correct answer must be A, B, C, D or the exact text of one option"])
        self.assertEqual(sorted(Question.objects.values_list("text", flat=True)),
                         ["Capital of France?", "What is 2 + 2?"])
        log = AuditLog.objects.get(action="questions.imported")
        self.assertEqual(log.institution_id, self.institution.pk)
        self.assertEqual(log.actor_id, self.educator.pk)
        self.assertEqual(log.metadata, {"created": 2, "skipped": 1})
        self.assertIn("Imported 2 questions", log.summary)
        self.assertIn("Geography, Maths", log.summary)

    def test_single_question_summary_is_singular(self):
        self.assertStatus(self.upload(HEADER + row(), commit=True), 201)
        self.assertIn("Imported 1 question (Maths)", AuditLog.objects.get(action="questions.imported").summary)

    def test_commit_with_no_valid_rows_is_400(self):
        response = self.upload(HEADER + row(answer="E") + row(question=""), commit=True)
        self.assertRejected(response, "None of the rows can be imported")
        self.assertFalse(AuditLog.objects.filter(action="questions.imported").exists())


# --------------------------------------------------------------------------- #
# File and header handling                                                    #
# --------------------------------------------------------------------------- #


class FileHandlingTests(ImportTestCase):
    def test_no_file_is_400(self):
        response = self.client.post(IMPORT, {"commit": "true"},
                                    HTTP_AUTHORIZATION=f"Bearer {create_token(self.educator)}")
        self.assertRejected(response, "Choose a CSV file")

    def test_header_case_spacing_and_hyphen_variants(self):
        header = " Subject , TOPIC,Difficulty,Question,Option A,option-a ,OPTION_B,Option  C,option-d,Correct Answer\n"
        # "Option A" and "option-a" are both option_a: the header repeats a column.
        self.assertRejected(self.upload(header + "x\n"), "repeats a column")

        header = " Subject , TOPIC,Difficulty,Question,Option A,option-b ,OPTION_C,Option  D,Correct-Answer\n"
        body = self.preview(header + "Maths,Arith,Easy,What is 2 + 2?,3,4,5,22,b\n")
        self.assertEqual(body["summary"]["valid"], 1)
        r = body["rows"][0]
        self.assertEqual(r["options"], {"A": "3", "B": "4", "C": "5", "D": "22"})
        self.assertEqual((r["correctAnswer"], r["difficulty"], r["topic"]), ("B", "easy", "Arith"))

    def test_aliases(self):
        for question_col, answer_col in (("text", "answer"), ("question_text", "correct"),
                                         ("Question Text", "correct_option"), ("question", "key")):
            with self.subTest(question_col=question_col, answer_col=answer_col):
                header = f"subject,level,{question_col},a,b,c,d,{answer_col}\n"
                body = self.preview(header + "Maths,hard,What is 2 + 2?,3,4,5,22,B\n")
                self.assertEqual(body["summary"]["valid"], 1, body)
                r = body["rows"][0]
                self.assertEqual((r["text"], r["difficulty"], r["correctAnswer"]), ("What is 2 + 2?", "hard", "B"))
                self.assertEqual(r["options"], {"A": "3", "B": "4", "C": "5", "D": "22"})

    def test_alias_and_canonical_name_together_repeat_a_column(self):
        header = "subject,question,option_a,option_b,option_c,option_d,answer,correct_answer\n"
        self.assertRejected(self.upload(header + "Maths,Q,1,2,3,4,A,A\n"), "repeats a column")

    def test_unknown_columns_are_ignored(self):
        header = "notes,subject,question,option_a,option_b,option_c,option_d,correct_answer,notes,owner\n"
        body = self.preview(header + "hello,Maths,What is 2 + 2?,3,4,5,22,B,again,me\n")
        self.assertEqual(body["summary"]["valid"], 1)
        self.assertEqual(body["rows"][0]["text"], "What is 2 + 2?")
        self.assertNotIn("notes", body["rows"][0])

    def test_optional_columns_may_be_absent(self):
        header = "subject,question,option_a,option_b,option_c,option_d,correct_answer\n"
        r = self.preview(header + "Maths,What is 2 + 2?,3,4,5,22,B\n")["rows"][0]
        self.assertEqual((r["topic"], r["difficulty"], r["explanation"], r["errors"]), ("", "medium", "", []))

    def test_missing_required_columns_are_named(self):
        message = self.assertRejected(self.upload("subject,question,option_a,option_b\nMaths,Q,1,2\n"),
                                      "Missing columns: option_c, option_d, correct_answer")
        self.assertIn("first row must be a header", message)
        self.assertRejected(self.upload("question,option_a,option_b,option_c,option_d,correct_answer\nQ,1,2,3,4,A\n"),
                            "Missing column: subject")

    def test_empty_file_and_blank_file(self):
        self.assertRejected(self.upload(b""), "The file is empty")
        self.assertRejected(self.upload(" , ,\n\n  \n"), "The file is empty")

    def test_header_only(self):
        self.assertRejected(self.upload(HEADER), "header but no questions")
        self.assertRejected(self.upload(HEADER + "\n,,,\n"), "header but no questions")

    def test_row_limit(self):
        rows = "".join(row(question=f"Question {i}?") for i in range(500))
        self.assertEqual(self.preview(HEADER + rows)["summary"]["valid"], 500)
        self.assertRejected(self.upload(HEADER + rows + row(question="One too many?")),
                            "Import at most 500 questions")

    def test_size_limit(self):
        big = HEADER + row(explanation="x" * (1024 * 1024))
        self.assertRejected(self.upload(big, commit=True), "larger than 1 MB")

    def test_invalid_csv(self):
        # A cell larger than the csv module's field limit makes the reader fail.
        content = HEADER + row(explanation="y" * 200_000)
        self.assertRejected(self.upload(content), "isn't valid CSV")

    def test_utf8_bom(self):
        body = self.preview(("﻿" + HEADER + row(subject="Café")).encode("utf-8"))
        self.assertEqual(body["summary"]["valid"], 1)
        self.assertEqual(body["rows"][0]["subject"], "Café")

    def test_cp1252(self):
        content = (HEADER + row(subject="Café", question="Which résumé format is best?",
                                options=("Chronological", "Functional", "Hybrid", "None – really"))).encode("cp1252")
        response = self.upload(content, commit=True)
        self.assertStatus(response, 201)
        q = Question.objects.get()
        self.assertEqual(q.subject, "Café")
        self.assertEqual(q.text, "Which résumé format is best?")
        self.assertEqual(q.options["D"], "None – really")

    def test_blank_lines_skipped_and_line_numbers(self):
        content = "\n" + HEADER + "\n" + row() + ",,,,\n\n" + row(question="Second?", answer="Z")
        body = self.preview(content)
        self.assertEqual(body["summary"], {"total": 2, "valid": 1, "invalid": 1})
        self.assertEqual([r["line"] for r in body["rows"]], [4, 7])

    def test_multiline_cells_do_not_shift_row_numbers(self):
        content = HEADER + row(explanation="First line\nsecond line") + "\n" + row(question="Second?", answer="Z") \
            + row()
        body = self.preview(content)
        self.assertEqual([r["line"] for r in body["rows"]], [2, 4, 5])
        self.assertEqual(body["rows"][0]["explanation"], "First line\nsecond line")
        self.assertEqual(body["rows"][2]["errors"], ["Same question as row 2"])

    def test_crlf_line_endings(self):
        content = (HEADER + row() + row(question="Second?")).replace("\n", "\r\n")
        body = self.preview(content)
        self.assertEqual([r["line"] for r in body["rows"]], [2, 3])
        self.assertEqual(body["rows"][1]["explanation"], "Adding.")

    def test_short_rows_are_padded(self):
        content = HEADER + "Maths,,,What is 2 + 2?,3,4\n"
        errors = self.preview(content)["rows"][0]["errors"]
        self.assertIn("Option C is missing or longer than 500 characters", errors)
        self.assertIn("Option D is missing or longer than 500 characters", errors)
        self.assertIn("Correct answer is missing", errors)


class DefaultSubjectTests(ImportTestCase):
    def test_fills_blank_cells(self):
        body = self.preview(HEADER + row(subject=""), subject="  Computer   Networks ")
        self.assertEqual(body["rows"][0]["subject"], "Computer Networks")
        self.assertEqual(body["rows"][0]["errors"], [])

    def test_does_not_override_filled_cells(self):
        body = self.preview(HEADER + row(subject="Physics") + row(subject="", question="Other?"),
                            subject="Networks")
        self.assertEqual([r["subject"] for r in body["rows"]], ["Physics", "Networks"])

    def test_lets_the_file_omit_the_subject_column(self):
        header = "question,option_a,option_b,option_c,option_d,correct_answer\n"
        response = self.upload(header + "What is 2 + 2?,3,4,5,22,B\n", commit=True, subject="Maths")
        self.assertStatus(response, 201)
        self.assertEqual(response.json()["subjects"], ["Maths"])
        q = Question.objects.get()
        self.assertEqual((q.subject, q.subject_key), ("Maths", "maths"))

    def test_blank_default_is_ignored(self):
        header = "question,option_a,option_b,option_c,option_d,correct_answer\n"
        self.assertRejected(self.upload(header + "Q,1,2,3,4,A\n", subject="   "), "Missing column: subject")

    def test_without_default_blank_subject_is_an_error(self):
        self.assertEqual(self.row_errors(row(subject="")), [["Subject is missing"]])


# --------------------------------------------------------------------------- #
# Row validation                                                              #
# --------------------------------------------------------------------------- #


class RowErrorTests(ImportTestCase):
    def test_missing_question(self):
        self.assertEqual(self.row_errors(row(question="")), [["Question is missing"]])

    def test_missing_and_too_long_options(self):
        errors = self.row_errors(row(options=("", "4", "x" * 501, "22")))[0]
        self.assertEqual(errors, ["Option A is missing or longer than 500 characters",
                                  "Option C is missing or longer than 500 characters"])
        self.assertEqual(self.row_errors(row(options=("3", "4", "x" * 500, "22"))), [[]])

    def test_missing_answer(self):
        self.assertEqual(self.row_errors(row(answer="")), [["Correct answer is missing"]])

    def test_bad_answers(self):
        bad = "Correct answer must be A, B, C, D or the exact text of one option"
        for answer in ("E", "Option E", "7", "four"):
            with self.subTest(answer=answer):
                self.assertEqual(self.row_errors(row(answer=answer)), [[bad]])
        # Text matching two identical options is ambiguous.
        self.assertEqual(self.row_errors(row(options=("Yes", "No", "yes", "Maybe"), answer="Yes")), [[bad]])

    def test_answer_variants(self):
        for answer in ("B", "b", "Option B", "option b", "B)", "b.", " B ", "OPTION B:"):
            with self.subTest(answer=answer):
                rows = self.preview(HEADER + row(answer=answer))["rows"]
                self.assertEqual((rows[0]["correctAnswer"], rows[0]["errors"]), ("B", []))

    def test_answer_by_option_text_ignores_case_and_spaces(self):
        rows = self.preview(HEADER + row(options=("Linked list", "Binary  tree", "Heap", "Queue"),
                                         answer="  binary tree "))["rows"]
        self.assertEqual((rows[0]["correctAnswer"], rows[0]["errors"]), ("B", []))

    def test_difficulty(self):
        self.assertEqual(self.row_errors(row(difficulty="extreme")), [["Difficulty must be easy, medium or hard"]])
        rows = self.preview(HEADER + row(difficulty="HARD") + row(question="Q2?", difficulty=""))["rows"]
        self.assertEqual([r["difficulty"] for r in rows], ["hard", "medium"])

    def test_length_limits(self):
        cases = (
            ({"question": "q" * 2000}, {"question": "q" * 2001}),
            ({"subject": "s" * 200}, {"subject": "s" * 201}),
            ({"topic": "t" * 120}, {"topic": "t" * 121}),
            ({"explanation": "e" * 2000}, {"explanation": "e" * 2001}),
        )
        for ok, too_long in cases:
            with self.subTest(field=next(iter(ok))):
                self.assertEqual(self.row_errors(row(**ok)), [[]])
                errors = self.row_errors(row(**too_long))[0]
                self.assertEqual(len(errors), 1)
                self.assertIn("too long", errors[0])

    def test_several_problems_reported_together(self):
        errors = self.row_errors(row(question="", subject="", difficulty="x", answer=""))[0]
        self.assertEqual(errors, ["Question is missing", "Subject is missing",
                                  "Difficulty must be easy, medium or hard", "Correct answer is missing"])

    def test_cells_are_trimmed(self):
        r = self.preview(HEADER + " Maths , Arith , easy ,  What is 2 + 2?  , 3 , 4 , 5 , 22 , B , Why \n")["rows"][0]
        self.assertEqual((r["subject"], r["topic"], r["text"], r["explanation"]),
                         ("Maths", "Arith", "What is 2 + 2?", "Why"))
        self.assertEqual(r["options"], {"A": "3", "B": "4", "C": "5", "D": "22"})


class DuplicateTests(ImportTestCase):
    def test_already_in_the_bank(self):
        self.bank(subject="Maths ", subject_key="maths")
        errors = self.row_errors(row(subject="  MATHS", question="what  is 2 +  2?"))
        self.assertEqual(errors, [["Already in the question bank"]])

    def test_same_text_under_another_subject_is_not_a_duplicate(self):
        self.bank()
        self.assertEqual(self.row_errors(row(subject="Arithmetic")), [[]])

    def test_another_institutions_question_is_not_a_duplicate(self):
        other = make_institution()
        self.bank(institution=other, created_by=make_user(other, "educator"))
        self.assertEqual(self.row_errors(row()), [[]])

    def test_duplicate_within_the_file(self):
        content = HEADER + row() + "\n" + row(question=" WHAT IS 2 + 2? ", subject="maths") + row(subject="Other")
        body = self.preview(content)
        self.assertEqual([r["errors"] for r in body["rows"]], [[], ["Same question as row 2"], []])
        self.assertEqual([r["line"] for r in body["rows"]], [2, 4, 5])

    def test_invalid_first_copy_does_not_block_a_later_valid_one(self):
        errors = self.row_errors(row(answer="E"), row())
        self.assertEqual(errors, [["Correct answer must be A, B, C, D or the exact text of one option"], []])

    def test_duplicate_within_file_imports_once(self):
        response = self.upload(HEADER + row() + row(), commit=True)
        self.assertStatus(response, 201)
        self.assertEqual((response.json()["created"], response.json()["skipped"]), (1, 1))
        self.assertEqual(Question.objects.count(), 1)


# --------------------------------------------------------------------------- #
# Writing a question by hand (POST /api/questions)                            #
# --------------------------------------------------------------------------- #


def manual(**overrides):
    item = {
        "text": "Which keyword declares a constant in JavaScript?",
        "options": {"A": "var", "B": "let", "C": "const", "D": "static"},
        "correctAnswer": "C",
        "subject": "JavaScript",
        "topic": "Basics",
        "difficulty": "easy",
        "explanation": "const bindings cannot be reassigned.",
        "aiGenerated": False,
    }
    item.update(overrides)
    return item


class ManualQuestionTests(ImportTestCase):
    def save(self, item, user=None):
        return self.api_post(QUESTIONS, {"questions": [item]}, user=user or self.educator)

    def test_saved_as_not_ai_generated(self):
        response = self.save(manual())
        self.assertStatus(response, 201)
        body = response.json()
        self.assertEqual(body["created"], 1)
        self.assertIs(body["questions"][0]["aiGenerated"], False)
        q = Question.objects.get()
        self.assertIs(q.ai_generated, False)
        self.assertEqual((q.created_by_id, q.institution_id), (self.educator.pk, self.institution.pk))
        self.assertEqual((q.subject_key, q.correct_answer, q.topic), ("javascript", "C", "Basics"))

    def test_missing_ai_flag_defaults_to_false(self):
        item = manual()
        del item["aiGenerated"]
        self.assertStatus(self.save(item, user=self.admin), 201)
        self.assertIs(Question.objects.get().ai_generated, False)

    def test_students_cannot_write_questions(self):
        self.assertStatus(self.save(manual(), user=self.student), 403)
        self.assertFalse(Question.objects.exists())

    def test_validation_errors_per_field(self):
        response = self.save(manual(text="  ", subject="", options={"A": "var", "B": "", "C": "x", "D": "y"},
                                    correctAnswer="E", difficulty="impossible", aiGenerated="no",
                                    topic="t" * 121))
        self.assertStatus(response, 400)
        body = response.json()
        self.assertEqual(body["message"], "Question 1: text is required")
        self.assertEqual(body["errors"], [{"index": 1, "errors": [
            "text is required",
            "subject is required",
            "topic is too long (max 120 characters)",
            "option B must be 1-500 characters of text",
            "correctAnswer must be A, B, C or D",
            "difficulty must be easy, medium or hard",
            "aiGenerated must be true or false",
        ]}])
        self.assertFalse(Question.objects.exists())

    def test_options_must_be_exactly_four(self):
        response = self.save(manual(options={"A": "1", "B": "2", "C": "3"}))
        self.assertStatus(response, 400)
        self.assertIn("options must have exactly A, B, C and D", response.json()["errors"][0]["errors"])
        self.assertFalse(Question.objects.exists())
