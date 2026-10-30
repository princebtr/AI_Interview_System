"""Proctoring vision: one YOLO pass (people, phones, phone look-alikes) plus the
YuNet face detector. The rules that turn detections into facts are in
ai/detection.py; settings.PROCTORING holds the models and thresholds."""
import io
import logging
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings
from PIL import Image, UnidentifiedImageError

from config.http import BadRequest

from . import detection

logger = logging.getLogger(__name__)

_object_model = None
_object_lock = threading.Lock()  # ultralytics predictors aren't safe to share across threads
_face_local = threading.local()  # one YuNet detector per thread (they are cheap)


def _cfg():
    return settings.PROCTORING


def _objects():
    global _object_model
    with _object_lock:
        if _object_model is None:
            from ultralytics import YOLO

            _object_model = YOLO(str(_cfg()["OBJECT_MODEL"]))
        return _object_model


def _faces_detector():
    path = Path(_cfg()["FACE_MODEL"])
    if not path.exists() or not hasattr(cv2, "FaceDetectorYN"):
        return None
    detector = getattr(_face_local, "detector", None)
    if detector is None:
        # Low score threshold here; detection.interpret applies the real ones.
        detector = cv2.FaceDetectorYN.create(str(path), "", (320, 320), 0.3, 0.3, 50)
        _face_local.detector = detector
    return detector


# Webcam frames are 0.3-2 MP; anything far bigger is not a camera frame and
# could be a tiny, highly compressed "decompression bomb".
MAX_PIXELS = 4_000_000


def read_image(upload):
    if upload is None:
        raise BadRequest("No image provided")
    if upload.size > settings.MAX_UPLOAD_BYTES:
        raise BadRequest("Image is too large")
    data = upload.read()
    if not data:
        raise BadRequest("File is not a valid image")

    # Read only the header first so huge dimensions are rejected before decoding.
    try:
        with Image.open(io.BytesIO(data)) as header:
            width, height = header.size
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise BadRequest("File is not a valid image")
    if width * height > MAX_PIXELS:
        raise BadRequest("Image dimensions are too large")

    try:
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    except cv2.error:
        frame = None
    if frame is None:
        raise BadRequest("File is not a valid image")
    return frame, data


def available():
    """Whether camera checks can run here (ultralytics installed, object model present)."""
    try:
        import ultralytics  # noqa: F401
    except ImportError:
        return False
    return Path(_cfg()["OBJECT_MODEL"]).exists()


def face_model_available():
    return _faces_detector() is not None


def _detect_objects(frame):
    model = _objects()
    cfg = _cfg()
    floor = min(cfg["PERSON_CONFIDENCE"], cfg["PHONE_SUSPECT_CONFIDENCE"], 0.2)
    with _object_lock:
        result = model.predict(
            source=frame, imgsz=cfg["INFERENCE_SIZE"], conf=floor, classes=detection.OBJECT_CLASSES, verbose=False
        )[0]
    return [(int(b.cls[0]), float(b.conf[0]), tuple(float(v) for v in b.xyxy[0].tolist())) for b in result.boxes]


def _detect_faces(frame):
    detector = _faces_detector()
    if detector is None:
        return []
    height, width = frame.shape[:2]
    scale = min(1.0, 640 / max(height, width))
    small = cv2.resize(frame, (int(width * scale), int(height * scale))) if scale < 1 else frame
    detector.setInputSize((small.shape[1], small.shape[0]))
    _, found = detector.detect(small)
    faces = []
    for f in found if found is not None else []:
        landmarks = [(float(f[4 + 2 * i]) / scale, float(f[5 + 2 * i]) / scale) for i in range(5)]
        faces.append((float(f[14]), tuple(float(v) / scale for v in f[:4]), landmarks))
    return faces


def analyse(frame):
    """Facts about one webcam frame (see detection.interpret). Nothing is stored."""
    started = time.perf_counter()
    objects = _detect_objects(frame)
    faces = _detect_faces(frame)
    height, width = frame.shape[:2]
    result = detection.interpret(objects, faces, width, height, _cfg())
    result["latencyMs"] = round((time.perf_counter() - started) * 1000)
    return result


# Used by the older interview endpoints (detect-faces, detect-phone).
def count_people(frame):
    return analyse(frame)["people"]


def phone_present(frame):
    return analyse(frame)["phone"]
