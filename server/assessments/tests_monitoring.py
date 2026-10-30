"""Monitored tests: settings, violations, thresholds, penalties, auto-submission, review."""
import uuid
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.tests import make_cohort, make_institution, make_user
from assessments import sitting
from assessments.models import Assessment, AssessmentAttempt, ViolationEvent
from assessments.tests_sitting import ASSESSMENTS, MY_TESTS, SittingTestCase

AVAILABLE = mock.patch("assessments.monitoring.vision.available", return_value=True)


class MonitoringTestCase(SittingTestCase):
    def monitored(self, starts_in=timedelta(minutes=-5), **overrides):
        test = self.schedule(starts_in=starts_in)
        fields = {"monitoring_enabled": True, **overrides}
        Assessment.objects.filter(pk=test.pk).update(**fields)
        test.refresh_from_db()
        return test

    def start(self, test, user=None):
        response = self.api_post(f"{MY_TESTS}/{test.pk}/start", user=user or self.student)
        self.assertStatus(response, 200)
        return [q["id"] for q in response.json()["attempt"]["questions"]]

    def report(self, test, kind, detail, event_id=None, user=None, **extra):
        body = {"eventId": event_id or uuid.uuid4().hex, "type": kind, "detail": detail, **extra}
        return self.api_post(f"{MY_TESTS}/{test.pk}/violations", body, user=user or self.student)

    def attempt(self):
        return AssessmentAttempt.objects.get(student=self.student)


class SettingsTests(MonitoringTestCase):
    def test_create_with_default_rules(self):
        with AVAILABLE:
            response = self.api_post(ASSESSMENTS, self.payload(monitoring={}), user=self.educator)
        self.assertStatus(response, 201)
        rules = response.json()["assessment"]["monitoring"]
        self.assertTrue(rules["enabled"])
        self.assertEqual(rules["limits"], {"screen_switch": 3, "voice": 5, "face": 5, "phone": 3})
        self.assertEqual(rules["facePenalty"], 5)

    def test_every_new_test_is_proctored_even_without_settings(self):
        with AVAILABLE:
            response = self.api_post(ASSESSMENTS, self.payload(), user=self.educator)
        self.assertStatus(response, 201)
        rules = response.json()["assessment"]["monitoring"]
        self.assertTrue(rules["enabled"])
        self.assertTrue(rules["fullscreenRequired"] and rules["cameraRequired"] and rules["microphoneRequired"])
        # Without the detection model, camera checks default to off instead of failing.
        with mock.patch("assessments.monitoring.vision.available", return_value=False):
            response = self.api_post(ASSESSMENTS, self.payload(), user=self.educator)
        self.assertStatus(response, 201)
        rules = response.json()["assessment"]["monitoring"]
        self.assertEqual((rules["enabled"], rules["cameraRequired"], rules["phoneDetection"]), (True, False, False))

    def test_proctoring_cannot_be_turned_off(self):
        with AVAILABLE:
            response = self.api_post(ASSESSMENTS, self.payload(monitoring={"enabled": False}), user=self.educator)
            self.assertFieldErrors(response, "monitoring.enabled")
            test = self.monitored()
            patch = self.request("PATCH", f"{ASSESSMENTS}/{test.pk}", {"monitoring": {"enabled": False}}, user=self.educator)
            self.assertFieldErrors(patch, "monitoring.enabled")
        self.assertTrue(Assessment.objects.get(pk=test.pk).monitoring_enabled)

    def test_custom_rules_and_validation(self):
        with AVAILABLE:
            ok = self.api_post(
                ASSESSMENTS,
                self.payload(monitoring={"maxScreenSwitches": 1, "facePenalty": 0, "microphoneRequired": False}),
                user=self.educator,
            )
            self.assertStatus(ok, 201)
            rules = ok.json()["assessment"]["monitoring"]
            self.assertEqual((rules["limits"]["screen_switch"], rules["facePenalty"], rules["microphoneRequired"]), (1, 0, False))

            bad = self.api_post(
                ASSESSMENTS, self.payload(monitoring={"maxVoiceViolations": -1, "facePenalty": 500}), user=self.educator
            )
            self.assertFieldErrors(bad, "monitoring.maxVoiceViolations", "monitoring.facePenalty")
            nothing = self.api_post(
                ASSESSMENTS,
                self.payload(monitoring={"fullscreenRequired": False, "cameraRequired": False, "microphoneRequired": False}),
                user=self.educator,
            )
            self.assertFieldErrors(nothing, "monitoring")

    def test_camera_checks_need_the_detection_model(self):
        with mock.patch("assessments.monitoring.vision.available", return_value=False):
            response = self.api_post(ASSESSMENTS, self.payload(monitoring={"cameraRequired": True}), user=self.educator)
            self.assertFieldErrors(response, "monitoring.cameraRequired")
            no_camera = self.api_post(ASSESSMENTS, self.payload(monitoring={"cameraRequired": False}), user=self.educator)
        self.assertStatus(no_camera, 201)
        self.assertFalse(no_camera.json()["assessment"]["monitoring"]["phoneDetection"])

    def test_rules_can_change_only_before_anyone_starts(self):
        test = self.monitored()
        url = f"{ASSESSMENTS}/{test.pk}"
        with AVAILABLE:
            changed = self.request("PATCH", url, {"monitoring": {"maxScreenSwitches": 5}}, user=self.educator)
            self.assertStatus(changed, 200)
            self.assertEqual(changed.json()["assessment"]["monitoring"]["limits"]["screen_switch"], 5)
            self.assertStatus(self.request("PATCH", url, {"monitoring": {}}, user=self.student), 403)
            colleague = make_user(self.institution, "educator")
            self.assertStatus(self.request("PATCH", url, {"monitoring": {}}, user=colleague), 404)
            self.start(test)
            self.assertStatus(self.request("PATCH", url, {"monitoring": {}}, user=self.educator), 400)


class ThresholdTests(MonitoringTestCase):
    CASES = [
        ("screen_switch", "fullscreen_exit", 3, "SCREEN_SWITCH_LIMIT"),
        ("voice", "sustained_speech", 5, "VOICE_VIOLATION_LIMIT"),
        ("face", "no_face", 5, "FACE_VIOLATION_LIMIT"),
        ("phone", "phone_detected", 3, "PHONE_DETECTION_LIMIT"),
    ]

    def test_each_limit_submits_automatically(self):
        for kind, detail, limit, reason in self.CASES:
            with self.subTest(kind=kind):
                AssessmentAttempt.objects.all().delete()
                test = self.monitored(face_violation_penalty=0)
                self.start(test)
                for n in range(1, limit):
                    body = self.report(test, kind, detail, confidence=0.9).json()
                    self.assertEqual((body["violation"]["countAfter"], body["violation"]["actionTaken"]), (n, "warned"))
                    self.assertEqual(body["test"]["attempt"]["status"], "in_progress")
                    self.assertEqual(body["test"]["attempt"]["monitoring"]["counts"][kind], n)
                last = self.report(test, kind, detail).json()
                self.assertEqual(last["violation"]["actionTaken"], "auto_submitted")
                result = last["test"]["attempt"]
                self.assertEqual((result["status"], result["submissionReason"], result["autoSubmitted"]), ("submitted", reason, True))
                # Nothing is accepted afterwards.
                self.assertStatus(self.report(test, kind, detail), 400)
                self.assertStatus(self.put_answers(test, {}), 400)
                test.delete()

    def test_a_limit_of_zero_only_warns(self):
        test = self.monitored(max_screen_switches=0)
        self.start(test)
        for _ in range(6):
            self.assertEqual(self.report(test, "screen_switch", "tab_hidden").json()["violation"]["actionTaken"], "warned")
        self.assertIsNone(self.attempt().submitted_at)
        self.assertEqual(self.attempt().screen_switch_count, 6)

    def test_answers_sent_with_the_last_violation_are_graded(self):
        test = self.monitored(max_screen_switches=1)
        ids = self.start(test)
        body = self.report(test, "screen_switch", "fullscreen_exit", answers={ids[0]: "B", ids[1]: "B"}, review=[ids[2]]).json()
        result = body["test"]["attempt"]
        self.assertEqual((result["status"], result["correct"], result["score"]), ("submitted", 2, 4))
        self.assertEqual(self.attempt().review, [ids[2]])

    def test_checks_the_test_does_not_use_are_refused(self):
        test = self.monitored(microphone_required=False, phone_detection_enabled=False)
        self.start(test)
        self.assertStatus(self.report(test, "voice", "sustained_speech"), 400)
        self.assertStatus(self.report(test, "phone", "phone_detected"), 400)
        self.assertStatus(self.report(test, "face", "smiling"), 400)
        self.assertStatus(self.report(test, "face", "no_face", event_id="bad id!"), 400)
        self.assertStatus(self.report(test, "face", "no_face", confidence=7), 400)

        unmonitored = self.schedule()  # e.g. started before proctoring existed
        Assessment.objects.filter(pk=unmonitored.pk).update(monitoring_enabled=False)
        self.start(unmonitored)
        self.assertStatus(self.report(unmonitored, "screen_switch", "fullscreen_exit"), 400)

    def test_technical_events_are_logged_but_not_counted(self):
        test = self.monitored()
        self.start(test)
        body = self.report(test, "technical", "camera_interrupted").json()
        self.assertEqual(body["violation"]["actionTaken"], "logged")
        attempt = self.attempt()
        self.assertEqual(attempt.violation_counts(), {"screen_switch": 0, "voice": 0, "face": 0, "phone": 0})
        self.assertEqual(attempt.monitoring_status, "degraded")
        self.report(test, "technical", "monitoring_resumed")
        self.assertEqual(self.attempt().monitoring_status, "active")

    def test_reports_after_the_close_finalise_the_attempt(self):
        test = self.monitored()
        self.start(test)
        Assessment.objects.filter(pk=test.pk).update(starts_at=timezone.now() - timedelta(hours=2))
        self.assertStatus(self.report(test, "face", "no_face"), 400)
        attempt = self.attempt()
        self.assertEqual((attempt.submission_reason, attempt.face_violation_count), ("TIME_LIMIT", 0))


class PenaltyTests(MonitoringTestCase):
    def test_face_violations_deduct_marks_once_each(self):
        test = self.monitored(face_violation_penalty=5)
        Assessment.objects.filter(pk=test.pk).update(marks_per_question=10)  # 4 questions = 40 marks
        test.refresh_from_db()
        ids = self.start(test)
        first = self.report(test, "face", "multiple_faces", event_id="face-event-1", confidence=0.83).json()
        self.assertEqual((first["violation"]["penaltyApplied"], first["test"]["attempt"]["monitoring"]["totalPenalty"]), (5, 5))
        # A retried or duplicated report changes nothing.
        again = self.report(test, "face", "multiple_faces", event_id="face-event-1")
        self.assertStatus(again, 200)
        self.assertFalse(again.json()["recorded"])
        self.report(test, "face", "no_face")
        self.assertEqual((self.attempt().face_violation_count, self.attempt().total_penalty), (2, 10))
        self.assertEqual(ViolationEvent.objects.filter(violation_type="face").count(), 2)

        result = self.api_post(f"{MY_TESTS}/{test.pk}/submit", {"answers": {i: "B" for i in ids}}, user=self.student).json()["attempt"]
        self.assertEqual((result["rawScore"], result["totalPenalty"], result["score"]), (40, 10, 30))
        self.assertEqual(result["submissionReason"], "STUDENT_SUBMITTED")
        self.assertEqual(result["percentage"], 75.0)

    def test_the_score_never_goes_below_zero(self):
        test = self.monitored(face_violation_penalty=50)
        ids = self.start(test)
        self.report(test, "face", "no_face")
        result = self.api_post(f"{MY_TESTS}/{test.pk}/submit", {"answers": {ids[0]: "B"}}, user=self.student).json()["attempt"]
        self.assertEqual((result["rawScore"], result["totalPenalty"], result["score"]), (2, 50, 0))

    def test_the_fifth_face_violation_is_penalised_and_submits(self):
        test = self.monitored(face_violation_penalty=1)
        ids = self.start(test)
        self.put_answers(test, {i: "B" for i in ids})  # 8 marks
        for _ in range(5):
            body = self.report(test, "face", "no_face").json()
        result = body["test"]["attempt"]
        self.assertEqual((result["submissionReason"], result["rawScore"], result["totalPenalty"], result["score"]), ("FACE_VIOLATION_LIMIT", 8, 5, 3))


class ConcurrencyTests(MonitoringTestCase):
    def test_an_attempt_is_finalised_exactly_once(self):
        test = self.monitored()
        self.start(test)
        attempt = self.attempt()
        first = sitting.grade(AssessmentAttempt.objects.get(pk=attempt.pk), reason="STUDENT_SUBMITTED")
        second = sitting.grade(AssessmentAttempt.objects.get(pk=attempt.pk), auto=True, reason="FACE_VIOLATION_LIMIT")
        self.assertTrue(first.graded_now)
        self.assertFalse(second.graded_now)
        self.assertEqual(second.submission_reason, "STUDENT_SUBMITTED")

    def test_duplicate_submit_requests_return_the_same_result(self):
        test = self.monitored()
        ids = self.start(test)
        url = f"{MY_TESTS}/{test.pk}/submit"
        one = self.api_post(url, {"answers": {ids[0]: "B"}}, user=self.student).json()["attempt"]
        two = self.api_post(url, {"answers": {i: "B" for i in ids}}, user=self.student).json()["attempt"]
        self.assertEqual((one["score"], two["score"]), (2, 2))
        self.assertEqual(one["submittedAt"], two["submittedAt"])

    def test_a_violation_after_submission_is_not_counted(self):
        test = self.monitored()
        self.start(test)
        self.report(test, "screen_switch", "fullscreen_exit", event_id="switch-event-1")
        self.api_post(f"{MY_TESTS}/{test.pk}/submit", {}, user=self.student)
        late = self.report(test, "screen_switch", "fullscreen_exit")
        self.assertStatus(late, 400)
        # The retry of an event recorded before submission is still answered.
        retry = self.report(test, "screen_switch", "fullscreen_exit", event_id="switch-event-1")
        self.assertStatus(retry, 200)
        self.assertFalse(retry.json()["recorded"])
        self.assertEqual(self.attempt().screen_switch_count, 1)


class RefreshTests(MonitoringTestCase):
    def test_reopening_the_test_restores_counts_and_answers(self):
        test = self.monitored()
        ids = self.start(test)
        self.report(test, "screen_switch", "left_page", answers={ids[0]: "C"})
        attempt = self.api_get(f"{MY_TESTS}/{test.pk}", user=self.student).json()["attempt"]
        self.assertEqual(attempt["answers"], {ids[0]: "C"})
        self.assertEqual(attempt["monitoring"]["counts"]["screen_switch"], 1)
        self.assertEqual(attempt["monitoring"]["limits"]["screen_switch"], 3)


class FrameTests(MonitoringTestCase):
    def post_frame(self, test):
        image = SimpleUploadedFile("frame.jpg", b"jpeg-bytes", content_type="image/jpeg")
        return self.client.post(f"{MY_TESTS}/{test.pk}/frame", {"image": image}, **self.auth(self.student))

    def patched(self, result=None, available=True):
        result = result or {"people": 1, "peopleConfidence": 0.91, "phone": True, "phoneConfidence": 0.7}
        return (
            mock.patch("assessments.monitoring.vision.available", return_value=available),
            mock.patch("assessments.monitoring.vision.read_image", return_value=(object(), b"")),
            mock.patch("assessments.monitoring.vision.analyse", return_value=dict(result)),
        )

    def test_frames_are_analysed_and_rate_limited(self):
        test = self.monitored()
        self.start(test)
        a, b, c = self.patched()
        with a, b, c:
            first = self.post_frame(test)
            self.assertStatus(first, 200)
            self.assertEqual(first.json()["people"], 1)
            self.assertStatus(self.post_frame(test), 429)
        attempt = self.attempt()
        self.assertEqual((attempt.frames_analysed, attempt.monitoring_status), (1, "active"))

    def test_phone_results_are_hidden_when_phone_detection_is_off(self):
        test = self.monitored(phone_detection_enabled=False)
        self.start(test)
        a, b, c = self.patched()
        with a, b, c:
            self.assertFalse(self.post_frame(test).json()["phone"])

    def test_a_failing_model_is_not_the_students_fault(self):
        test = self.monitored()
        self.start(test)
        a, b, c = self.patched()
        with a, b, mock.patch("assessments.monitoring.vision.analyse", side_effect=RuntimeError("weights corrupt")):
            self.assertStatus(self.post_frame(test), 503)
        self.assertEqual(self.attempt().violation_counts(), {"screen_switch": 0, "voice": 0, "face": 0, "phone": 0})

    def test_unavailable_or_unused_camera_checks(self):
        test = self.monitored()
        self.start(test)
        a, b, c = self.patched(available=False)
        with a, b, c:
            self.assertStatus(self.post_frame(test), 503)
        no_camera = self.monitored(camera_required=False)
        AssessmentAttempt.objects.all().delete()
        self.start(no_camera)
        a, b, c = self.patched()
        with a, b, c:
            self.assertStatus(self.post_frame(no_camera), 400)


class ReviewAndAccessTests(MonitoringTestCase):
    def setUp(self):
        super().setUp()
        self.test = self.monitored(face_violation_penalty=3)
        ids = self.start(self.test)
        self.report(self.test, "face", "no_face", event_id="face-event-a")
        self.report(self.test, "face", "multiple_faces", event_id="face-event-b")
        self.report(self.test, "technical", "camera_interrupted")
        self.api_post(f"{MY_TESTS}/{self.test.pk}/submit", {"answers": {i: "B" for i in ids}}, user=self.student)
        self.url = f"{ASSESSMENTS}/{self.test.pk}/violations"

    def test_results_and_timeline_for_staff(self):
        detail = self.api_get(f"{ASSESSMENTS}/{self.test.pk}", user=self.educator).json()
        row = next(r for r in detail["results"] if r["student"]["id"] == str(self.student.pk))
        self.assertEqual((row["rawScore"], row["totalPenalty"], row["score"]), (8, 6, 2))
        self.assertEqual(row["violations"]["face"], 2)
        self.assertEqual(row["submissionReason"], "STUDENT_SUBMITTED")

        events = self.api_get(self.url, {"student": str(self.student.pk)}, user=self.educator).json()["events"]
        self.assertEqual([e["type"] for e in events], ["face", "face", "technical"])
        self.assertEqual(events[0]["student"]["name"], self.student.name)

    def test_monitoring_records_are_restricted(self):
        self.assertStatus(self.api_get(self.url, user=self.student), 403)
        self.assertStatus(self.api_get(self.url, user=make_user(self.institution, "educator")), 404)
        self.assertStatus(self.api_get(self.url, user=make_user(make_institution(), "admin")), 404)
        self.assertStatus(self.api_get(self.url, user=make_user(self.institution, "admin")), 200)
        self.assertStatus(self.api_get(self.url, {"student": "not-an-id"}, user=self.educator), 404)
        # A student can't report into someone else's test.
        outsider = make_user(self.institution, "student", cohort=make_cohort(self.institution))
        self.assertStatus(self.report(self.test, "face", "no_face", user=outsider), 404)

    def test_dismissing_a_violation_refunds_its_penalty(self):
        event = ViolationEvent.objects.get(event_id="face-event-a")
        url = f"{self.url}/{event.pk}"
        dismissed = self.request("PATCH", url, {"reviewStatus": "dismissed"}, user=self.educator)
        self.assertStatus(dismissed, 200)
        self.assertEqual((dismissed.json()["attempt"]["totalPenalty"], dismissed.json()["attempt"]["score"]), (3, 5))
        upheld = self.request("PATCH", url, {"reviewStatus": "upheld"}, user=self.educator)
        self.assertEqual(upheld.json()["attempt"]["score"], 2)
        self.assertStatus(self.request("PATCH", url, {"reviewStatus": "maybe"}, user=self.educator), 400)
        self.assertStatus(self.request("PATCH", url, {"reviewStatus": "dismissed"}, user=self.student), 403)
        technical = ViolationEvent.objects.get(violation_type="technical")
        self.assertStatus(self.request("PATCH", f"{self.url}/{technical.pk}", {"reviewStatus": "dismissed"}, user=self.educator), 400)

    def test_violations_can_only_be_reviewed_after_submission(self):
        other = make_user(self.institution, "student", cohort=self.cohort)
        self.start(self.test, user=other)
        self.report(self.test, "face", "no_face", event_id="face-event-open", user=other)
        event = ViolationEvent.objects.get(event_id="face-event-open")
        self.assertStatus(self.request("PATCH", f"{self.url}/{event.pk}", {"reviewStatus": "dismissed"}, user=self.educator), 400)


class ProctorUpcomingTestsMigrationTests(MonitoringTestCase):
    """assessments/migrations/0004: proctoring is switched on for tests nobody has started."""

    def run_migration(self, camera=True):
        import importlib

        from django.apps import apps

        migration = importlib.import_module("assessments.migrations.0004_proctor_every_test")
        with mock.patch("ai.vision.available", return_value=camera):
            migration.proctor_upcoming_tests(apps, None)

    def legacy(self, **kwargs):
        test = self.schedule(**kwargs)
        Assessment.objects.filter(pk=test.pk).update(monitoring_enabled=False)
        return test

    def test_only_unstarted_open_tests_change(self):
        upcoming = self.legacy(starts_in=timedelta(hours=1))
        started = self.legacy()
        self.start(started)
        over = self.legacy(starts_in=timedelta(hours=-3))
        self.run_migration()
        flags = {t.pk: t.monitoring_enabled for t in Assessment.objects.all()}
        self.assertEqual((flags[upcoming.pk], flags[started.pk], flags[over.pk]), (True, False, False))

    def test_without_the_detection_model_camera_checks_stay_off(self):
        upcoming = self.legacy(starts_in=timedelta(hours=1))
        self.run_migration(camera=False)
        upcoming.refresh_from_db()
        self.assertEqual(
            (upcoming.monitoring_enabled, upcoming.camera_required, upcoming.phone_detection_enabled), (True, False, False)
        )
