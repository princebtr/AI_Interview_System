"""Proctoring detection: the rules that turn model output into facts
(ai/detection.py), the real models on sample images, and the interview's
camera-check endpoints."""
import os
from unittest import mock, skipUnless

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.conf import settings

from accounts.auth import create_token
from accounts.tests import make_user
from ai import detection, vision
from ai.tests import PracticeTestCase

CFG = {
    "PERSON_CONFIDENCE": 0.5,
    "FACE_CONFIDENCE": 0.6,
    "FACE_RESCUE_CONFIDENCE": 0.8,
    "PHONE_SUSPECT_CONFIDENCE": 0.25,
    "PHONE_CONFIDENCE": 0.35,
    "LOOKALIKE_IOU": 0.5,
    "LOOK_AWAY_YAW": 0.6,
}
W, H = 640, 480
FRONT = [(100, 100), (140, 100), (120, 120), (105, 140), (135, 140)]  # nose between the eyes
TURNED = [(100, 100), (140, 100), (150, 120), (105, 140), (135, 140)]  # nose past the left eye


def person(conf, box=(100, 50, 400, 480)):
    return (detection.PERSON, conf, box)


def phone(conf, box=(300, 300, 360, 420)):
    return (detection.PHONE, conf, box)


def face(conf, landmarks=FRONT):
    return (conf, (90, 80, 70, 80), landmarks)


def facts(objects=(), faces=()):
    return detection.interpret(list(objects), list(faces), W, H, CFG)


class PeopleTests(SimpleTestCase):
    def test_empty_frame(self):
        result = facts()
        self.assertEqual((result["people"], result["faces"], result["lookingAway"]), (0, 0, False))

    def test_one_person_facing_the_camera(self):
        result = facts([person(0.9)], [face(0.95)])
        self.assertEqual((result["people"], result["faces"], result["lookingAway"]), (1, 1, False))

    def test_weak_person_boxes_are_ignored(self):
        self.assertEqual(facts([person(0.4)])["people"], 0)

    def test_a_confident_face_proves_someone_is_there(self):
        # Close webcam framing: YOLO misses the person, YuNet sees the face.
        self.assertEqual(facts([], [face(0.85)])["people"], 1)
        self.assertEqual(facts([], [face(0.7)])["people"], 0)  # not confident enough on its own

    def test_two_people_or_two_confident_faces_are_multiple(self):
        self.assertEqual(facts([person(0.9), person(0.6, (420, 60, 630, 480))])["people"], 2)
        self.assertEqual(facts([person(0.9)], [face(0.9), face(0.85)])["people"], 2)

    def test_looking_away_is_reported_but_is_not_absence(self):
        turned = facts([person(0.9)], [face(0.9, TURNED)])
        self.assertEqual((turned["people"], turned["lookingAway"]), (1, True))
        hidden = facts([person(0.9)], [])  # body in view, face not turned to the camera
        self.assertEqual((hidden["people"], hidden["lookingAway"]), (1, True))

    def test_yaw_ratio(self):
        self.assertAlmostEqual(detection.yaw_ratio(FRONT), 0.0)
        self.assertAlmostEqual(detection.yaw_ratio(TURNED), 0.75)
        self.assertEqual(detection.yaw_ratio([(100, 100), (100.5, 100), (150, 120)]), 0.0)  # eyes overlap


class PhoneTests(SimpleTestCase):
    def test_states(self):
        none, suspected, detected = facts([phone(0.2)]), facts([phone(0.3)]), facts([phone(0.7)])
        self.assertEqual((none["phoneSuspected"], none["phone"]), (False, False))
        self.assertEqual((suspected["phoneSuspected"], suspected["phone"]), (True, False))
        self.assertEqual((detected["phoneSuspected"], detected["phone"]), (True, True))
        self.assertEqual(detected["phoneConfidence"], 0.7)

    def test_boxes_are_normalised_and_most_confident_first(self):
        result = facts([phone(0.4, (0, 0, 64, 48)), phone(0.8, (320, 240, 640, 480))])
        self.assertEqual(result["phoneBoxes"], [[0.5, 0.5, 1.0, 1.0, 0.8], [0.0, 0.0, 0.1, 0.1, 0.4]])

    def test_a_phone_box_on_a_more_confident_lookalike_is_dropped(self):
        remote = (65, 0.7, (300, 300, 360, 425))
        self.assertFalse(facts([phone(0.5), remote])["phoneSuspected"])
        # A less confident look-alike, or one elsewhere, doesn't hide the phone.
        self.assertTrue(facts([phone(0.5), (65, 0.4, (300, 300, 360, 425))])["phone"])
        self.assertTrue(facts([phone(0.5), (65, 0.9, (0, 0, 50, 50))])["phone"])

    def test_iou(self):
        self.assertEqual(detection.iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)
        self.assertEqual(detection.iou((0, 0, 10, 10), (20, 20, 30, 30)), 0.0)
        self.assertAlmostEqual(detection.iou((0, 0, 10, 10), (5, 0, 15, 10)), 1 / 3)


class ConfigTests(SimpleTestCase):
    def test_client_config_comes_from_settings(self):
        config = detection.client_config(settings.PROCTORING)
        self.assertEqual(
            set(config), {"frameIntervalMs", "absence", "multiple", "phone", "clearRatio", "cooldownMs", "cameraGraceMs"}
        )
        self.assertEqual(set(config["phone"]), {"window", "positives"})

    def test_thresholds_are_tunable(self):
        strict = {**CFG, "PHONE_CONFIDENCE": 0.9}
        self.assertFalse(detection.interpret([phone(0.7)], [], W, H, strict)["phone"])


SAMPLES = None
try:
    import ultralytics

    SAMPLES = os.path.join(os.path.dirname(ultralytics.__file__), "assets")
except ImportError:
    pass


@skipUnless(SAMPLES and vision.available(), "detection models not installed")
class RealModelTests(SimpleTestCase):
    """The real models on ultralytics' sample photos (no mocks)."""

    def analyse(self, name):
        with open(os.path.join(SAMPLES, name), "rb") as f:
            frame, _ = vision.read_image(SimpleUploadedFile(name, f.read(), content_type="image/jpeg"))
        return vision.analyse(frame)

    def test_two_people(self):
        result = self.analyse("zidane.jpg")
        self.assertGreaterEqual(result["people"], 2)
        self.assertFalse(result["phone"])
        self.assertIn("latencyMs", result)

    def test_blank_frame(self):
        import numpy as np

        result = vision.analyse(np.full((480, 640, 3), 40, "uint8"))
        self.assertEqual((result["people"], result["phone"], result["phoneSuspected"]), (0, False, False))


class InterviewCameraTests(PracticeTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def post_frame(self, user=None):
        image = SimpleUploadedFile("frame.jpg", b"jpeg-bytes", content_type="image/jpeg")
        token = create_token(user or self.student)
        return self.client.post("/api/ai/analyse-frame", {"image": image}, HTTP_AUTHORIZATION=f"Bearer {token}")

    def patched(self, analyse=None):
        return (
            mock.patch("ai.vision.available", return_value=True),
            mock.patch("ai.vision.read_image", return_value=(object(), b"")),
            mock.patch("ai.vision.analyse", **(analyse or {"return_value": {"people": 1, "phone": False}})),
        )

    def test_config(self):
        response = self.api_get("/api/ai/proctoring-config", user=self.student)
        self.assertStatus(response, 200)
        self.assertEqual(response.json()["detection"], detection.client_config(settings.PROCTORING))
        self.assertStatus(self.api_get("/api/ai/proctoring-config", user=self.educator), 403)

    def test_frames_are_analysed_and_rate_limited_per_student(self):
        a, b, c = self.patched()
        with a, b, c:
            self.assertEqual(self.post_frame().json()["people"], 1)
            self.assertStatus(self.post_frame(), 429)
            other = make_user(self.institution, "student", cohort=self.cohort)
            self.assertStatus(self.post_frame(user=other), 200)

    @override_settings(PROCTORING={**settings.PROCTORING, "MIN_SERVER_INTERVAL_MS": 1000})
    def test_failures_are_not_the_students_fault(self):
        a, b, c = self.patched({"side_effect": RuntimeError("weights corrupt")})
        with a, b, c:
            self.assertStatus(self.post_frame(), 503)
        with mock.patch("ai.vision.available", return_value=False):
            self.assertStatus(self.post_frame(), 503)
        self.assertStatus(self.post_frame(user=self.educator), 403)
