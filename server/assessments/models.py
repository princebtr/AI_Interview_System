from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from ai import detection


class Question(models.Model):
    """A reviewed, reusable multiple-choice question in an institution's bank."""

    DIFFICULTY_CHOICES = [("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")]
    TYPE_CHOICES = [("mcq", "Multiple choice")]

    institution = models.ForeignKey(
        "institutions.Institution", on_delete=models.CASCADE, related_name="questions"
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="questions"
    )
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="mcq")
    subject = models.CharField(max_length=200)
    subject_key = models.CharField(max_length=200, db_index=True)
    topic = models.CharField(max_length=120, blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default="medium")
    text = models.TextField()
    options = models.JSONField()  # {"A": ..., "B": ..., "C": ..., "D": ...}
    correct_answer = models.CharField(max_length=1)
    explanation = models.TextField(blank=True)
    ai_generated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def to_dict(self):
        return {
            "id": str(self.pk),
            "type": self.type,
            "subject": self.subject,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "text": self.text,
            "options": self.options,
            "correctAnswer": self.correct_answer,
            "explanation": self.explanation,
            "aiGenerated": self.ai_generated,
            "createdBy": (
                {"id": str(self.created_by_id), "name": self.created_by.name}
                if self.created_by_id
                else None
            ),
            "createdAt": self.created_at,
        }


class Assessment(models.Model):
    """A scheduled multiple-choice test assigned to one cohort.

    The test opens at `starts_at` and closes for everyone `duration_minutes`
    later, like an exam sitting. `questions` is a snapshot taken when the test
    is created, so later edits to the question bank can't change it.
    """

    institution = models.ForeignKey(
        "institutions.Institution", on_delete=models.CASCADE, related_name="assessments"
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="assessments"
    )
    cohort = models.ForeignKey(
        "institutions.Cohort", on_delete=models.PROTECT, related_name="assessments"
    )
    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=200, blank=True)
    instructions = models.TextField(blank=True)
    starts_at = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveIntegerField()
    marks_per_question = models.PositiveIntegerField()
    # [{"id", "text", "options": {"A".."D"}, "correctAnswer", "explanation"}]
    questions = models.JSONField()
    shuffle_questions = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Proctoring (see assessments/monitoring.py). Every test is proctored; only
    # tests that had started before proctoring existed have it off. A limit of 0
    # means "warn only".
    monitoring_enabled = models.BooleanField(default=True)
    fullscreen_required = models.BooleanField(default=True)
    camera_required = models.BooleanField(default=True)
    microphone_required = models.BooleanField(default=True)
    phone_detection_enabled = models.BooleanField(default=True)
    max_screen_switches = models.PositiveSmallIntegerField(default=3)
    max_voice_violations = models.PositiveSmallIntegerField(default=5)
    max_face_violations = models.PositiveSmallIntegerField(default=5)
    face_violation_penalty = models.PositiveSmallIntegerField(default=5)  # marks per face violation
    max_phone_violations = models.PositiveSmallIntegerField(default=3)

    class Meta:
        ordering = ["starts_at"]

    @property
    def ends_at(self):
        return self.starts_at + timedelta(minutes=self.duration_minutes)

    @property
    def question_count(self):
        return len(self.questions)

    @property
    def total_marks(self):
        return self.question_count * self.marks_per_question

    def status(self, now=None):
        now = now or timezone.now()
        if now < self.starts_at:
            return "scheduled"
        return "live" if now < self.ends_at else "closed"

    def summary(self):
        return {
            "id": str(self.pk),
            "title": self.title,
            "subject": self.subject,
            "instructions": self.instructions,
            "cohort": self.cohort.to_dict(),
            "startsAt": self.starts_at,
            "endsAt": self.ends_at,
            "durationMinutes": self.duration_minutes,
            "questionCount": self.question_count,
            "marksPerQuestion": self.marks_per_question,
            "totalMarks": self.total_marks,
            "shuffleQuestions": self.shuffle_questions,
            "status": self.status(),
            "createdBy": (
                {"id": str(self.created_by_id), "name": self.created_by.name} if self.created_by_id else None
            ),
            "createdAt": self.created_at,
            "monitoring": self.monitoring_config(),
        }

    def monitoring_config(self):
        return {
            "enabled": self.monitoring_enabled,
            "fullscreenRequired": self.fullscreen_required,
            "cameraRequired": self.camera_required,
            "microphoneRequired": self.microphone_required,
            "phoneDetection": self.camera_required and self.phone_detection_enabled,
            "limits": {
                "screen_switch": self.max_screen_switches,
                "voice": self.max_voice_violations,
                "face": self.max_face_violations,
                "phone": self.max_phone_violations,
            },
            "facePenalty": self.face_violation_penalty,
            "detection": detection.client_config(settings.PROCTORING),
        }


class AssessmentAttempt(models.Model):
    """One student's sitting of an assessment (one per student)."""

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="assessment_attempts"
    )
    order = models.JSONField()  # question ids in the order this student sees them
    answers = models.JSONField(default=dict)  # {question id: "A".."D"}
    review = models.JSONField(default=list)  # question ids marked for review
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    auto_submitted = models.BooleanField(default=False)
    correct = models.PositiveIntegerField(null=True, blank=True)
    # Marks: raw_score from answers; score = max(0, raw_score - total_penalty).
    raw_score = models.FloatField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    total_penalty = models.FloatField(default=0)
    submission_reason = models.CharField(max_length=32, blank=True)

    # Monitoring state; counters only ever change through monitoring.record_violation.
    screen_switch_count = models.PositiveIntegerField(default=0)
    voice_violation_count = models.PositiveIntegerField(default=0)
    face_violation_count = models.PositiveIntegerField(default=0)
    phone_violation_count = models.PositiveIntegerField(default=0)
    monitoring_status = models.CharField(max_length=16, default="off")  # off | active | degraded
    frames_analysed = models.PositiveIntegerField(default=0)
    last_frame_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assessment", "student"], name="one_attempt_per_student")
        ]

    @property
    def final_score(self):
        """Marks after penalties, floored at zero (None until submitted)."""
        if self.submitted_at is None:
            return None
        if self.score is not None:
            return self.score
        return max(0.0, (self.raw_score or 0) - (self.total_penalty or 0))

    def violation_counts(self):
        return {
            "screen_switch": self.screen_switch_count,
            "voice": self.voice_violation_count,
            "face": self.face_violation_count,
            "phone": self.phone_violation_count,
        }


class ViolationEvent(models.Model):
    """One confirmed monitoring event during an attempt.

    `event_id` comes from the browser; (attempt, event_id) is unique, so a retried
    or duplicated report can never be counted or penalised twice.
    """

    TYPES = ("screen_switch", "voice", "face", "phone", "technical")

    attempt = models.ForeignKey(AssessmentAttempt, on_delete=models.CASCADE, related_name="violations")
    event_id = models.CharField(max_length=64)
    violation_type = models.CharField(max_length=16)
    detail = models.CharField(max_length=32, blank=True)  # e.g. fullscreen_exit, no_face, multiple_faces
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    confidence = models.FloatField(null=True, blank=True)
    action_taken = models.CharField(max_length=24)  # warned | penalised | auto_submitted | logged | ignored
    penalty_applied = models.FloatField(default=0)
    count_after = models.PositiveIntegerField(null=True, blank=True)
    review_status = models.CharField(max_length=12, default="unreviewed")  # unreviewed | upheld | dismissed
    reviewed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["occurred_at"]
        constraints = [
            models.UniqueConstraint(fields=["attempt", "event_id"], name="one_violation_per_event_id")
        ]
