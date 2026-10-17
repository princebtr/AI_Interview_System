from django.db import models
from django.utils import timezone


class InterviewSession(models.Model):
    institution = models.ForeignKey(
        "institutions.Institution", null=True, blank=True, on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    screenshot_path = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, default="started")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PracticeQuiz(models.Model):
    """A generated multiple-choice set held on the server, so a student's
    answers are graded against answer keys they never received."""

    institution = models.ForeignKey("institutions.Institution", on_delete=models.CASCADE)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    subject = models.CharField(max_length=200)
    questions = models.JSONField()  # [{id, question, options, correctAnswer, explanation}]
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answers = models.JSONField(default=dict)  # what was graded, saved at submission
    submission_reason = models.CharField(max_length=32, blank=True)

    # Proctoring (ai/proctoring.py): the same checks and limits as a default
    # scheduled test. Counters only change through proctoring.record_event.
    proctored = models.BooleanField(default=True)
    camera_checks = models.BooleanField(default=True)  # the server could run them when it was created
    screen_switch_count = models.PositiveIntegerField(default=0)
    voice_violation_count = models.PositiveIntegerField(default=0)
    face_violation_count = models.PositiveIntegerField(default=0)
    phone_violation_count = models.PositiveIntegerField(default=0)
    monitoring_status = models.CharField(max_length=16, default="off")  # off | active | degraded
    frames_analysed = models.PositiveIntegerField(default=0)
    last_frame_at = models.DateTimeField(null=True, blank=True)


class PracticeViolation(models.Model):
    """One confirmed proctoring event during a practice test (see ViolationEvent
    for scheduled tests). (quiz, event_id) is unique: retries count once."""

    quiz = models.ForeignKey(PracticeQuiz, on_delete=models.CASCADE, related_name="violations")
    event_id = models.CharField(max_length=64)
    violation_type = models.CharField(max_length=16)
    detail = models.CharField(max_length=32, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    confidence = models.FloatField(null=True, blank=True)
    action_taken = models.CharField(max_length=24)  # warned | auto_submitted | logged | ignored
    penalty_applied = models.FloatField(default=0)  # always 0: practice has no mark penalties
    count_after = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["occurred_at"]
        constraints = [
            models.UniqueConstraint(fields=["quiz", "event_id"], name="one_practice_violation_per_event_id")
        ]


class PracticeQuestion(models.Model):
    """An AI interview question issued to a student, answerable once."""

    institution = models.ForeignKey("institutions.Institution", on_delete=models.CASCADE)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    subject = models.CharField(max_length=200)
    text = models.TextField()
    answered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PracticeAttempt(models.Model):
    """One scored piece of student practice: a submitted quiz or an interview answer."""

    KIND_CHOICES = [("mcq", "Practice test"), ("interview", "AI interview answer")]

    institution = models.ForeignKey(
        "institutions.Institution", on_delete=models.CASCADE, related_name="practice_attempts"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="practice_attempts"
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    subject = models.CharField(max_length=200)
    subject_key = models.CharField(max_length=200, db_index=True)  # for grouping "Java" / "java "
    score = models.FloatField()  # 0-100
    correct = models.PositiveIntegerField(null=True, blank=True)
    total = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def key_for(subject):
        return " ".join(subject.split()).casefold()

    def to_dict(self):
        return {
            "id": str(self.pk),
            "kind": self.kind,
            "subject": self.subject,
            "score": round(self.score, 1),
            "correct": self.correct,
            "total": self.total,
            "createdAt": self.created_at,
        }
