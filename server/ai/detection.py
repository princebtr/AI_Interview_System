"""Turning raw model detections into proctoring facts for one webcam frame.

Pure functions (no models), so the rules are unit-tested and easy to tune.
Thresholds come from settings.PROCTORING; see README "Tuning proctoring".

Why two models: YOLO's person class is reliable for whole people but misses
close head-and-shoulders webcam framing in poor light; YuNet finds faces, and
a confident face then proves someone is present. Measured on labelled COCO
crops, YOLO11m people >= 0.5 plus a YuNet "rescue" at >= 0.8 got single-person
webcam frames right 98% of the time (vs 89% before).
"""

PERSON = 0
PHONE = 67
# COCO classes most often confused with phones: a phone box sitting on a more
# confident one of these is dropped.
LOOKALIKES = {62: "tv", 63: "laptop", 64: "mouse", 65: "remote", 66: "keyboard", 73: "book"}
OBJECT_CLASSES = [PERSON, PHONE, *LOOKALIKES]


def iou(a, b):
    """Intersection over union of two (x1, y1, x2, y2) boxes."""
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def yaw_ratio(landmarks):
    """How far the nose sits from the middle of the eyes, in eye distances.
    ~0 when facing the camera, beyond ~0.6 when the head is clearly turned.
    YuNet landmarks: right eye, left eye, nose tip, right and left mouth corners."""
    (rex, _), (lex, _), (nx, _) = landmarks[0], landmarks[1], landmarks[2]
    distance = abs(lex - rex)
    if distance < 1:
        return 0.0
    return (nx - (rex + lex) / 2) / distance


def interpret(objects, faces, width, height, cfg):
    """
    objects: [(class_id, confidence, (x1, y1, x2, y2))] from the object model
    faces:   [(confidence, (x, y, w, h), [(x, y) * 5 landmarks])] from the face model
    Returns the facts the browser tracks over time (see utils/proctoring.js).
    """
    persons = [c for k, c, _ in objects if k == PERSON and c >= cfg["PERSON_CONFIDENCE"]]
    visible = [f for f in faces if f[0] >= cfg["FACE_CONFIDENCE"]]
    sure = [f for f in faces if f[0] >= cfg["FACE_RESCUE_CONFIDENCE"]]

    if len(persons) >= 2 or len(sure) >= 2:
        people = max(len(persons), len(sure))
    else:
        people = 1 if persons or sure else 0

    candidates = []
    for k, c, box in objects:
        if k != PHONE or c < cfg["PHONE_SUSPECT_CONFIDENCE"]:
            continue
        covered = any(
            k2 in LOOKALIKES and c2 > c and iou(box, box2) > cfg["LOOKALIKE_IOU"] for k2, c2, box2 in objects
        )
        if not covered:
            candidates.append((c, box))
    phone_confidence = max((c for c, _ in candidates), default=0.0)

    looking_away = False
    if people == 1:
        if not visible:
            looking_away = True  # someone is there but no face is turned to the camera
        elif len(visible) == 1 and abs(yaw_ratio(visible[0][2])) > cfg["LOOK_AWAY_YAW"]:
            looking_away = True

    return {
        "people": people,
        "peopleConfidence": round(max(persons + [f[0] for f in faces], default=0.0), 3),
        "faces": len(visible),
        "faceConfidence": round(max((f[0] for f in faces), default=0.0), 3),
        "lookingAway": looking_away,
        "phone": phone_confidence >= cfg["PHONE_CONFIDENCE"],
        "phoneSuspected": phone_confidence >= cfg["PHONE_SUSPECT_CONFIDENCE"],
        "phoneConfidence": round(phone_confidence, 3),
        # Normalised boxes (0-1) so the browser can draw them over any preview size.
        "phoneBoxes": [
            [round(b[0] / width, 4), round(b[1] / height, 4), round(b[2] / width, 4), round(b[3] / height, 4), round(c, 3)]
            for c, b in sorted(candidates, reverse=True)[:3]
        ],
    }


def client_config(cfg):
    """The timing and evidence rules the browser applies (milliseconds)."""
    return {
        "frameIntervalMs": cfg["FRAME_INTERVAL_MS"],
        "absence": dict(cfg["ABSENCE"]),
        "multiple": dict(cfg["MULTIPLE"]),
        "phone": dict(cfg["PHONE"]),
        "clearRatio": cfg["CLEAR_RATIO"],
        "cooldownMs": cfg["COOLDOWN_MS"],
        "cameraGraceMs": cfg["CAMERA_GRACE_MS"],
    }
