"""Practice tests are proctored like scheduled tests: once-only events, limits
that submit automatically (graded once), camera checks, and student-only access."""
import uuid
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.tests import make_user
from ai.models import PracticeAttempt, PracticeQuiz, PracticeViolation
from ai.tests import EVALUATE_MCQ, PracticeTestCase

PRACTICE = "/api/ai/practice"
AVAILABLE = mock.patch("ai.vision.available", return_value=True)


class PracticeProctoringTestCase(PracticeTestCase):
    def new_quiz(self, camera=True, user=None):
        with mock.patch("ai.vision.available", return_value=camera):
            response = self.generate_quiz(user=user)
        self.assertStatus(response, 200)
        return response.json()

    def report(self, quiz_id, kind, detail, event_id=None, user=None, **extra):
        body = {"eventId": event_id or uuid.uuid4().hex, "type": kind, "detail": detail, **extra}
        return self.api_post(f"{PRACTICE}/{quiz_id}/violations", body, user=user or self.student)

    def quiz(self):
        return PracticeQuiz.objects.get()


class PracticeRulesTests(PracticeProctoringTestCase):
    def test_new_practice_tests_are_proctored_with_the_default_rules(self):
        body = self.new_quiz()
        rules = body["monitoring"]
        self.assertTrue(rules["enabled"])
        self.assertTrue(rules["fullscreenRequired"] and rules["cameraRequired"] and rules["microphoneRequired"])
        self.assertEqual(rules["limits"], {"screen_switch": 3, "voice": 5, "face": 5, "phone": 3})
        self.assertEqual(rules["facePenalty"], 0)  # practice is scored as a percentage
        self.assertEqual(rules["counts"], {"screen_switch": 0, "voice": 0, "face": 0, "phone": 0})

    def test_without_the_detection_model_camera_checks_are_off(self):
        rules = self.new_quiz(camera=False)["monitoring"]
        self.assertEqual((rules["cameraRequired"], rules["phoneDetection"]), (False, False))
        quiz_id = self.new_quiz(camera=False)["quizId"]
        self.assertStatus(self.report(quiz_id, "face", "no_face"), 400)
        self.assertStatus(self.report(quiz_id, "phone", "phone_detected"), 400)
        self.assertStatus(self.report(quiz_id, "voice", "sustained_speech"), 200)


class PracticeViolationTests(PracticeProctoringTestCase):
    def test_warnings_count_once_per_event(self):
        quiz_id = self.new_quiz()["quizId"]
        first = self.report(quiz_id, "face", "multiple_faces", event_id="practice-face-1", confidence=0.8).json()
        self.assertEqual((first["recorded"], first["violation"]["actionTaken"], first["violation"]["countAfter"]), (True, "warned", 1))
        self.assertEqual(first["violation"]["penaltyApplied"], 0)
        self.assertFalse(first["submitted"])
        again = self.report(quiz_id, "face", "multiple_faces", event_id="practice-face-1").json()
        self.assertFalse(again["recorded"])
        self.assertEqual(self.quiz().face_violation_count, 1)
        self.assertEqual(PracticeViolation.objects.count(), 1)

    def test_reaching_a_limit_grades_the_answers_sent_once(self):
        quiz_id = self.new_quiz()["quizId"]
        answers = {"1": "B", "2": "b", "3": "A"}
        for n in (1, 2):
            body = self.report(quiz_id, "screen_switch", "fullscreen_exit", answers=answers).json()
            self.assertEqual((body["violation"]["countAfter"], body["submitted"]), (n, False))
        last = self.report(quiz_id, "screen_switch", "tab_hidden", event_id="practice-switch-3", answers=answers).json()
        self.assertEqual((last["violation"]["actionTaken"], last["submitted"]), ("auto_submitted", True))
        result = last["result"]
        self.assertEqual((result["score"], result["totalQuestions"], result["percentage"]), (2, 4, 50.0))
        self.assertEqual(result["submissionReason"], "SCREEN_SWITCH_LIMIT")
        self.assertEqual(result["monitoring"]["counts"]["screen_switch"], 3)
        attempt = PracticeAttempt.objects.get()
        self.assertEqual((attempt.kind, attempt.score, attempt.correct), ("mcq", 50.0, 2))

        # Nothing more is accepted, and nothing is graded twice.
        self.assertStatus(self.report(quiz_id, "voice", "sustained_speech"), 400)
        self.assertStatus(self.api_post(EVALUATE_MCQ, {"quizId": quiz_id, "userAnswers": {"1": "B"}}, user=self.student), 400)
        # A retry of the report that submitted it gets the result again.
        retry = self.report(quiz_id, "screen_switch", "tab_hidden", event_id="practice-switch-3").json()
        self.assertEqual((retry["recorded"], retry["submitted"], retry["result"]["score"]), (False, True, 2))
        self.assertEqual(PracticeAttempt.objects.count(), 1)

    def test_the_student_submitting_records_the_reason_and_counts(self):
        quiz_id = self.new_quiz()["quizId"]
        self.report(quiz_id, "voice", "sustained_speech", confidence=0.7)
        body = self.api_post(EVALUATE_MCQ, {"quizId": quiz_id, "userAnswers": {"1": "B", "2": "B"}}, user=self.student).json()
        self.assertEqual((body["score"], body["submissionReason"]), (2, "STUDENT_SUBMITTED"))
        self.assertEqual(body["monitoring"]["counts"]["voice"], 1)
        self.assertStatus(self.report(quiz_id, "voice", "sustained_speech"), 400)

    def test_technical_events_are_logged_not_counted(self):
        quiz_id = self.new_quiz()["quizId"]
        body = self.report(quiz_id, "technical", "camera_interrupted").json()
        self.assertEqual(body["violation"]["actionTaken"], "logged")
        quiz = self.quiz()
        self.assertEqual((quiz.monitoring_status, quiz.screen_switch_count + quiz.face_violation_count), ("degraded", 0))

    def test_bad_reports_are_refused_and_nothing_is_stored(self):
        quiz_id = self.new_quiz()["quizId"]
        self.assertStatus(self.report(quiz_id, "face", "smiling"), 400)
        self.assertStatus(self.report(quiz_id, "face", "no_face", event_id="no!"), 400)
        self.assertStatus(self.report(quiz_id, "face", "no_face", confidence=3), 400)
        self.assertStatus(self.report(quiz_id, "face", "no_face", answers=["B"]), 400)
        self.assertFalse(PracticeViolation.objects.exists())
        self.assertEqual(self.quiz().face_violation_count, 0)

    def test_quizzes_created_before_proctoring_are_not_proctored(self):
        quiz_id = self.new_quiz()["quizId"]
        PracticeQuiz.objects.filter(pk=quiz_id).update(proctored=False)
        self.assertStatus(self.report(quiz_id, "screen_switch", "fullscreen_exit"), 400)


class PracticeAccessTests(PracticeProctoringTestCase):
    def test_only_the_student_who_owns_the_quiz(self):
        quiz_id = self.new_quiz()["quizId"]
        other = make_user(self.institution, "student", cohort=self.cohort)
        self.assertStatus(self.report(quiz_id, "screen_switch", "fullscreen_exit", user=other), 404)
        self.assertStatus(self.api_get(f"{PRACTICE}/{quiz_id}", user=other), 404)
        self.assertStatus(self.report(quiz_id, "screen_switch", "fullscreen_exit", user=self.educator), 403)
        self.assertStatus(self.report("not-an-id", "screen_switch", "fullscreen_exit"), 404)
        self.assertFalse(PracticeViolation.objects.exists())

    def test_status_shows_the_result_once_submitted(self):
        quiz_id = self.new_quiz()["quizId"]
        before = self.api_get(f"{PRACTICE}/{quiz_id}", user=self.student).json()
        self.assertEqual((before["submitted"], before["result"]), (False, None))
        self.api_post(EVALUATE_MCQ, {"quizId": quiz_id, "userAnswers": {"1": "B"}}, user=self.student)
        after = self.api_get(f"{PRACTICE}/{quiz_id}", user=self.student).json()
        self.assertEqual((after["submitted"], after["result"]["score"]), (True, 1))
        self.assertNotIn("correctAnswer", str(before))


class PracticeFrameTests(PracticeProctoringTestCase):
    def post_frame(self, quiz_id, user=None):
        image = SimpleUploadedFile("frame.jpg", b"jpeg-bytes", content_type="image/jpeg")
        return self.client.post(
            f"{PRACTICE}/{quiz_id}/frame", {"image": image}, **{"HTTP_AUTHORIZATION": f"Bearer {self.token(user)}"}
        )

    def token(self, user=None):
        from accounts.auth import create_token

        return create_token(user or self.student)

    def patched(self, available=True, analyse=None):
        return (
            mock.patch("ai.vision.available", return_value=available),
            mock.patch("ai.vision.read_image", return_value=(object(), b"")),
            mock.patch(
                "ai.vision.analyse",
                **(analyse or {"return_value": {"people": 1, "peopleConfidence": 0.9, "phone": False, "phoneConfidence": 0.1}}),
            ),
        )

    def test_frames_are_analysed_and_rate_limited(self):
        quiz_id = self.new_quiz()["quizId"]
        a, b, c = self.patched()
        with a, b, c:
            first = self.post_frame(quiz_id)
            self.assertStatus(first, 200)
            self.assertEqual(first.json()["people"], 1)
            self.assertStatus(self.post_frame(quiz_id), 429)
        quiz = self.quiz()
        self.assertEqual((quiz.frames_analysed, quiz.monitoring_status), (1, "active"))

    def test_refusals(self):
        quiz_id = self.new_quiz()["quizId"]
        a, b, c = self.patched(available=False)
        with a, b, c:
            self.assertStatus(self.post_frame(quiz_id), 503)
        a, b, c = self.patched(analyse={"side_effect": RuntimeError("weights corrupt")})
        with a, b, c:
            self.assertStatus(self.post_frame(quiz_id), 503)
        other = make_user(self.institution, "student", cohort=self.cohort)
        a, b, c = self.patched()
        with a, b, c:
            self.assertStatus(self.post_frame(quiz_id, user=other), 404)
        self.api_post(EVALUATE_MCQ, {"quizId": quiz_id, "userAnswers": {"1": "B"}}, user=self.student)
        with a, b, c:
            self.assertStatus(self.post_frame(quiz_id), 400)  # already submitted

        no_camera = self.new_quiz(camera=False)["quizId"]
        with a, b, c:
            self.assertStatus(self.post_frame(no_camera), 400)
