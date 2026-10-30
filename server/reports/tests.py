"""Tests for performance reports: a student's own (/me), any student's for staff
(/students/<id>) and the institution/group overview (/overview).

The backend has no transactions, so every fixture is built in setUp() (see
accounts/tests.py). MongoDB stores datetimes to the millisecond, so timestamps
compared with API output are created without microseconds.
"""
from datetime import datetime, time, timedelta

from bson import ObjectId
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.tests import (
    ApiTestCase,
    make_batch,
    make_cohort,
    make_department,
    make_institution,
    make_section,
    make_user,
)
from ai.models import PracticeAttempt
from assessments.models import Assessment, AssessmentAttempt

ME = "/api/reports/me"
OVERVIEW = "/api/reports/overview"


def student_url(student_id):
    return f"/api/reports/students/{student_id}"


def now_ms():
    """Now, truncated to the millisecond precision MongoDB keeps."""
    now = timezone.now()
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def practice(user, score, kind="mcq", subject="Java", at=None):
    attempt = PracticeAttempt.objects.create(
        institution=user.institution,
        user=user,
        kind=kind,
        subject=subject,
        subject_key=PracticeAttempt.key_for(subject),
        score=score,
    )
    if at is not None:
        PracticeAttempt.objects.filter(pk=attempt.pk).update(created_at=at)
    return attempt


def make_test(institution, audience, title="Test", *, starts_ago=timedelta(days=2), duration=30,
              questions=4, marks=5, creator=None, subject="Java"):
    """A scheduled test assigned to `audience`, starting `starts_ago` before now
    (so it is closed when starts_ago > duration, live otherwise)."""
    test = Assessment(
        institution=institution,
        created_by=creator,
        title=title,
        subject=subject,
        starts_at=now_ms() - starts_ago,
        duration_minutes=duration,
        marks_per_question=marks,
        shuffle_questions=False,
        questions=[
            {"id": f"q{n}", "text": f"Q{n}?", "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
             "correctAnswer": "B", "explanation": ""}
            for n in range(1, questions + 1)
        ],
    )
    test.set_audience(audience)
    test.save()
    return test


def submit(test, student, *, score=None, raw=None, penalty=0.0, at=None):
    """A submitted attempt. `score` is the stored final; leave it None to have
    the final derived from raw - penalty."""
    if at is None:
        at = min(test.starts_at + timedelta(minutes=10), now_ms() - timedelta(seconds=30))
    return AssessmentAttempt.objects.create(
        assessment=test,
        student=student,
        order=[q["id"] for q in test.questions],
        submitted_at=at,
        score=score,
        raw_score=raw if raw is not None else score,
        total_penalty=penalty,
    )


def local_midnight(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def monday(ts):
    day = timezone.localtime(ts).date()
    return day - timedelta(days=day.weekday())


def expected_weeks(days):
    today = timezone.localdate()
    first = today - timedelta(days=days - 1)
    week, last, weeks = first - timedelta(days=first.weekday()), today - timedelta(days=today.weekday()), []
    while week <= last:
        weeks.append(week.isoformat())
        week += timedelta(days=7)
    return weeks


class ReportsTestCase(ApiTestCase):
    """Institution A: B1 > D1 > S1 > {C1, C2}, B1 > D1 > S2 > C3, B1 > D2 > S3 > C4,
    and an empty batch B2. Institution B is another tenant."""

    def setUp(self):
        self.inst = make_institution("Alpha College")
        self.b1 = make_batch(self.inst, "B1")
        self.b2 = make_batch(self.inst, "B2")
        self.d1 = make_department(self.b1, "D1")
        self.d2 = make_department(self.b1, "D2")
        self.s1 = make_section(self.d1, "S1")
        self.s2 = make_section(self.d1, "S2")
        self.s3 = make_section(self.d2, "S3")
        self.c1 = make_cohort(self.inst, "C1", section=self.s1)
        self.c2 = make_cohort(self.inst, "C2", section=self.s1)
        self.c3 = make_cohort(self.inst, "C3", section=self.s2)
        self.c4 = make_cohort(self.inst, "C4", section=self.s3)

        self.admin = make_user(self.inst, "admin", name="Admin")
        self.educator = make_user(self.inst, "educator", name="Educator")
        self.ann = make_user(self.inst, "student", name="Ann", cohort=self.c1)
        self.ben = make_user(self.inst, "student", name="Ben", cohort=self.c1)
        self.cat = make_user(self.inst, "student", name="Cat", cohort=self.c2)
        self.dan = make_user(self.inst, "student", name="Dan", cohort=self.c4)
        self.eve = make_user(self.inst, "student", name="Eve")  # not placed

        self.other = make_institution("Beta College")
        self.other_cohort = make_cohort(self.other, "Other cohort")
        self.other_admin = make_user(self.other, "admin")
        self.other_student = make_user(self.other, "student", name="Outsider", cohort=self.other_cohort)

    def get_ok(self, path, user, params=None):
        response = self.api_get(path, params, user=user)
        self.assertStatus(response, 200)
        return response.json()


# --------------------------------------------------------------------------- #
# Access control                                                              #
# --------------------------------------------------------------------------- #


class AccessTests(ReportsTestCase):
    def test_unauthenticated_requests_are_rejected(self):
        for path in (ME, OVERVIEW, student_url(self.ann.pk)):
            with self.subTest(path=path):
                self.assertStatus(self.api_get(path), 401)

    def test_my_report_is_for_students_only(self):
        self.get_ok(ME, self.ann)
        for user in (self.admin, self.educator):
            with self.subTest(role=user.role):
                self.assertStatus(self.api_get(ME, user=user), 403)

    def test_staff_endpoints_reject_students(self):
        for path in (OVERVIEW, student_url(self.ann.pk), student_url(self.ben.pk)):
            with self.subTest(path=path):
                self.assertStatus(self.api_get(path, user=self.ann), 403)

    def test_staff_can_read_overview_and_student_reports(self):
        for user in (self.admin, self.educator):
            with self.subTest(role=user.role):
                self.get_ok(OVERVIEW, user)
                self.get_ok(student_url(self.ann.pk), user)

    def test_student_report_not_found(self):
        cases = {
            "other tenant's student": str(self.other_student.pk),
            "staff member": str(self.educator.pk),
            "admin": str(self.admin.pk),
            "unknown id": str(ObjectId()),
            "malformed id": "not-an-id",
        }
        for label, student_id in cases.items():
            with self.subTest(case=label):
                response = self.api_get(student_url(student_id), user=self.admin)
                self.assertStatus(response, 404)
                self.assertEqual(response.json()["message"], "Student not found")

    def test_other_tenant_staff_cannot_read_student(self):
        self.assertStatus(self.api_get(student_url(self.ann.pk), user=self.other_admin), 404)

    def test_only_get_is_allowed(self):
        self.assertStatus(self.api_post(ME, {}, user=self.ann), 405)
        self.assertStatus(self.api_post(OVERVIEW, {}, user=self.admin), 405)


# --------------------------------------------------------------------------- #
# ?days= and the window                                                       #
# --------------------------------------------------------------------------- #


class DaysTests(ReportsTestCase):
    def test_default_is_90_days(self):
        for path, user in ((ME, self.ann), (OVERVIEW, self.admin), (student_url(self.ann.pk), self.admin)):
            with self.subTest(path=path):
                body = self.get_ok(path, user)
                self.assertEqual(body["range"]["days"], 90)
                start = parse_datetime(body["range"]["from"])
                self.assertEqual(start, local_midnight(timezone.localdate() - timedelta(days=89)))

    def test_accepted_values(self):
        for days in (30, 90, 180, 365):
            for path, user in ((ME, self.ann), (OVERVIEW, self.admin), (student_url(self.ann.pk), self.admin)):
                with self.subTest(days=days, path=path):
                    body = self.get_ok(path, user, {"days": str(days)})
                    self.assertEqual(body["range"]["days"], days)
                    self.assertEqual(len(body["trend"]), len(expected_weeks(days)))

    def test_other_values_are_rejected(self):
        for days in ("7", "abc", "0", "-30", "30.0", "1000"):
            for path, user in ((ME, self.ann), (OVERVIEW, self.admin), (student_url(self.ann.pk), self.admin)):
                with self.subTest(days=days, path=path):
                    response = self.api_get(path, {"days": days}, user=user)
                    self.assertStatus(response, 400)
                    self.assertIn("days must be one of 30, 90, 180, 365", response.json()["message"])

    def test_window_boundary_for_practice(self):
        now = timezone.now()
        practice(self.ann, 10, at=now - timedelta(days=30, hours=1))  # before the 30-day window
        practice(self.ann, 80, at=now - timedelta(days=28))  # inside it
        body = self.get_ok(ME, self.ann, {"days": "30"})
        self.assertEqual(body["summary"]["practiceTests"], 1)
        self.assertEqual(body["summary"]["practiceAverage"], 80.0)
        self.assertEqual(len(body["recent"]), 1)

        body = self.get_ok(ME, self.ann, {"days": "90"})
        self.assertEqual(body["summary"]["practiceTests"], 2)
        self.assertEqual(body["summary"]["practiceAverage"], 45.0)

        overview = self.get_ok(OVERVIEW, self.admin, {"days": "30"})
        self.assertEqual(overview["summary"]["practiceSessions"], 1)

    def test_window_boundary_for_tests(self):
        old = make_test(self.inst, self.c1, "Old", starts_ago=timedelta(days=31))
        recent = make_test(self.inst, self.c1, "Recent", starts_ago=timedelta(days=20))
        submit(old, self.ann, score=10)
        submit(recent, self.ann, score=20)
        body = self.get_ok(ME, self.ann, {"days": "30"})
        self.assertEqual([t["title"] for t in body["tests"]], ["Recent"])
        self.assertEqual(body["summary"]["testAverage"], 100.0)
        body = self.get_ok(ME, self.ann, {"days": "90"})
        self.assertEqual([t["title"] for t in body["tests"]], ["Recent", "Old"])
        self.assertEqual(body["summary"]["testAverage"], 75.0)

    def test_trend_weeks_and_weekly_numbers(self):
        now = timezone.now()
        this_week = now - timedelta(seconds=5)
        last_week = now - timedelta(days=7)
        practice(self.ann, 80, at=this_week)
        practice(self.ann, 60, at=this_week)
        practice(self.ann, 40, kind="interview", at=this_week)
        practice(self.ann, 50, at=last_week)
        test = make_test(self.inst, self.c1, starts_ago=timedelta(hours=2))
        submit(test, self.ann, score=15, at=now_ms() - timedelta(minutes=1))  # 75%

        body = self.get_ok(ME, self.ann, {"days": "30"})
        trend = body["trend"]
        self.assertEqual([p["week"] for p in trend], expected_weeks(30))
        by_week = {p["week"]: p for p in trend}
        cur, prev = monday(this_week).isoformat(), monday(last_week).isoformat()
        self.assertEqual(
            by_week[cur], {"week": cur, "practice": 70.0, "interview": 40.0, "tests": 75.0, "sessions": 3}
        )
        self.assertEqual(
            by_week[prev], {"week": prev, "practice": 50.0, "interview": None, "tests": None, "sessions": 1}
        )
        for week, point in by_week.items():
            if week not in (cur, prev):
                self.assertEqual(point["sessions"], 0)
                self.assertIsNone(point["practice"])
        self.assertNotIn("activeStudents", trend[0])

        # The overview's trend also counts active students per week.
        practice(self.ben, 100, at=this_week)
        overview = self.get_ok(OVERVIEW, self.admin, {"days": "30"})
        by_week = {p["week"]: p for p in overview["trend"]}
        self.assertEqual([p["week"] for p in overview["trend"]], expected_weeks(30))
        self.assertEqual(by_week[cur]["activeStudents"], 2)
        self.assertEqual(by_week[cur]["sessions"], 4)
        self.assertEqual(by_week[cur]["practice"], 80.0)
        self.assertEqual(by_week[prev]["activeStudents"], 1)


# --------------------------------------------------------------------------- #
# One student                                                                 #
# --------------------------------------------------------------------------- #


class StudentReportTests(ReportsTestCase):
    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.newest = local_midnight(today) + timedelta(seconds=1)
        # Ann: practice today and yesterday (a 2-day streak), and 3 days ago.
        practice(self.ann, 80, at=self.newest)
        practice(self.ann, 60, at=local_midnight(today - timedelta(days=1)) + timedelta(hours=12))
        practice(self.ann, 50, kind="interview", subject="Python",
                 at=local_midnight(today - timedelta(days=3)) + timedelta(hours=12))
        practice(self.ben, 90)  # cohort mate
        practice(self.cat, 10)  # same section, other cohort: not a mate
        practice(self.other_student, 0)

        # Tests: 4 questions x 5 marks = 20.
        days = timedelta(days=1)
        self.t1 = make_test(self.inst, self.c1, "T1 cohort", starts_ago=5 * days)
        self.t2 = make_test(self.inst, self.b1, "T2 batch", starts_ago=4 * days)
        self.t4 = make_test(self.inst, self.c2, "T4 other cohort", starts_ago=3 * days)
        self.t5 = make_test(self.inst, self.d2, "T5 not assigned but taken", starts_ago=2 * days)
        self.t6 = make_test(self.inst, self.d1, "T6 left open", starts_ago=1 * days)
        self.t3 = make_test(self.inst, self.s1, "T3 live", starts_ago=timedelta(minutes=5), duration=60)
        self.t7 = make_test(self.inst, self.c3, "T7 other section", starts_ago=6 * days)
        make_test(self.other, self.other_cohort, "Foreign", starts_ago=2 * days)

        submit(self.t1, self.ann, score=15)  # 75%
        submit(self.t1, self.ben, raw=12, penalty=2)  # final 10 -> 50%
        submit(self.t2, self.ben, score=20)  # 100%
        submit(self.t4, self.cat, score=4)  # 20%
        submit(self.t5, self.ann, score=10)  # 50%
        # Left open when the test closed: two correct answers -> 10 marks -> 50%.
        AssessmentAttempt.objects.create(
            assessment=self.t6, student=self.ann, order=["q1", "q2", "q3", "q4"],
            answers={"q1": "B", "q2": "B", "q3": "A"},
        )

    def check_report(self, body):
        summary = body["summary"]
        self.assertEqual(summary["practiceAverage"], 70.0)  # practice tests only
        self.assertEqual(summary["practiceTests"], 2)
        self.assertEqual(summary["interviewAverage"], 50.0)
        self.assertEqual(summary["interviewAnswers"], 1)
        self.assertEqual(summary["overallPracticeAverage"], round(190 / 3, 1))
        self.assertEqual(summary["testAverage"], round((75 + 50 + 50) / 3, 1))
        self.assertEqual(summary["testsTaken"], 3)
        self.assertEqual(summary["testsMissed"], 1)
        self.assertEqual(summary["streakDays"], 2)
        self.assertEqual(summary["cohortPracticeAverage"], 90.0)  # Ben only
        self.assertEqual(summary["cohortTestAverage"], 75.0)  # Ben: 50 and 100

        rows = {t["title"]: t for t in body["tests"]}
        self.assertEqual(
            [t["title"] for t in body["tests"]],
            ["T3 live", "T6 left open", "T5 not assigned but taken", "T2 batch", "T1 cohort"],
        )
        self.assertEqual(rows["T1 cohort"]["status"], "submitted")
        self.assertEqual(rows["T1 cohort"]["percentage"], 75.0)
        self.assertEqual(rows["T1 cohort"]["groupAverage"], 62.5)
        self.assertEqual(rows["T1 cohort"]["id"], str(self.t1.pk))
        self.assertEqual(rows["T1 cohort"]["subject"], "Java")
        self.assertEqual((rows["T2 batch"]["status"], rows["T2 batch"]["percentage"]), ("missed", None))
        self.assertEqual(rows["T2 batch"]["groupAverage"], 100.0)
        self.assertEqual((rows["T3 live"]["status"], rows["T3 live"]["percentage"]), ("open", None))
        self.assertIsNone(rows["T3 live"]["groupAverage"])
        self.assertEqual(rows["T5 not assigned but taken"]["status"], "submitted")
        self.assertEqual(rows["T5 not assigned but taken"]["percentage"], 50.0)
        self.assertEqual((rows["T6 left open"]["status"], rows["T6 left open"]["percentage"]), ("submitted", 50.0))

        self.assertEqual(
            body["subjects"],
            [
                {"subject": "Java", "attempts": 2, "averageScore": 70.0},
                {"subject": "Python", "attempts": 1, "averageScore": 50.0},
            ],
        )
        self.assertEqual([r["score"] for r in body["recent"]], [80, 60, 50])  # newest first
        self.assertEqual(set(body["recent"][0]), {"id", "kind", "subject", "score", "correct", "total", "createdAt"})

    def test_my_report(self):
        body = self.get_ok(ME, self.ann)
        self.check_report(body)
        self.assertEqual(body["student"]["id"], str(self.ann.pk))
        self.assertEqual(body["student"]["placement"]["label"], "B1 · D1 · S1 · C1")

    def test_attempt_left_open_is_finalized(self):
        self.get_ok(ME, self.ann)
        attempt = AssessmentAttempt.objects.get(assessment=self.t6, student=self.ann)
        self.assertIsNotNone(attempt.submitted_at)
        self.assertEqual(attempt.submitted_at, self.t6.ends_at)
        self.assertTrue(attempt.auto_submitted)
        self.assertEqual(attempt.score, 10.0)

    def test_staff_report_has_the_same_shape_plus_the_student(self):
        mine = self.get_ok(ME, self.ann)
        for user in (self.admin, self.educator):
            with self.subTest(role=user.role):
                body = self.get_ok(student_url(self.ann.pk), user)
                self.assertEqual(set(body), set(mine))
                self.assertEqual(set(body), {"student", "range", "summary", "trend", "subjects", "tests", "recent"})
                self.check_report(body)
                student = body["student"]
                self.assertEqual(student["id"], str(self.ann.pk))
                self.assertEqual(student["name"], "Ann")
                self.assertEqual(student["email"], self.ann.email)
                self.assertEqual(student["placement"]["label"], "B1 · D1 · S1 · C1")
                self.assertEqual(student["placement"]["cohort"], {"id": str(self.c1.pk), "name": "C1"})
                self.assertIn("lastLogin", student)

    def test_test_assigned_to_an_ancestor_counts_for_descendant_cohorts(self):
        # Cat (C2, under S1 / D1 / B1): T2 (batch), T3 (section), T6 (department) and T4 (her cohort).
        body = self.get_ok(student_url(self.cat.pk), self.admin)
        statuses = {t["title"]: t["status"] for t in body["tests"]}
        self.assertEqual(
            statuses,
            {"T3 live": "open", "T6 left open": "missed", "T4 other cohort": "submitted", "T2 batch": "missed"},
        )
        self.assertEqual(body["summary"]["testsMissed"], 2)
        self.assertEqual(body["summary"]["testAverage"], 20.0)
        self.assertIsNone(body["summary"]["cohortPracticeAverage"])  # no mates in C2
        self.assertIsNone(body["summary"]["cohortTestAverage"])

        # Dan (C4, under D2 / B1): T2 (batch) and T5 (department D2) only.
        body = self.get_ok(student_url(self.dan.pk), self.admin)
        self.assertEqual({t["title"]: t["status"] for t in body["tests"]},
                         {"T5 not assigned but taken": "missed", "T2 batch": "missed"})

    def test_unplaced_student_has_no_missed_tests(self):
        practice(self.eve, 55)
        body = self.get_ok(ME, self.eve)
        self.assertEqual(body["tests"], [])
        self.assertEqual(body["summary"]["testsMissed"], 0)
        self.assertEqual(body["summary"]["testsTaken"], 0)
        self.assertIsNone(body["summary"]["testAverage"])
        self.assertIsNone(body["summary"]["cohortPracticeAverage"])
        self.assertIsNone(body["summary"]["cohortTestAverage"])
        self.assertEqual(body["summary"]["practiceAverage"], 55.0)
        self.assertIsNone(body["student"]["placement"])

    def test_unplaced_student_still_sees_tests_they_took(self):
        submit(self.t1, self.eve, score=5)
        body = self.get_ok(ME, self.eve)
        self.assertEqual([(t["title"], t["status"], t["percentage"]) for t in body["tests"]],
                         [("T1 cohort", "submitted", 25.0)])

    def test_empty_report(self):
        body = self.get_ok(student_url(self.other_student.pk), self.other_admin)
        summary = body["summary"]
        self.assertEqual(summary["practiceAverage"], 0.0)
        self.assertEqual(summary["streakDays"], 1)
        self.assertEqual(summary["testsTaken"], 0)
        self.assertEqual([t["title"] for t in body["tests"]], ["Foreign"])
        self.assertEqual(body["tests"][0]["status"], "missed")

    def test_recent_is_capped_at_ten(self):
        for n in range(12):
            practice(self.ben, n, at=now_ms() - timedelta(minutes=n + 1))
        body = self.get_ok(student_url(self.ben.pk), self.admin)
        self.assertEqual(len(body["recent"]), 10)
        self.assertEqual(body["summary"]["practiceTests"], 13)
        times = [parse_datetime(r["createdAt"]) for r in body["recent"]]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_subjects_are_capped_and_ordered(self):
        for n in range(12):
            practice(self.ben, 50, subject=f"Subject {n:02d}")
        practice(self.ben, 70, subject="subject 05")  # same subject, newer spelling
        body = self.get_ok(student_url(self.ben.pk), self.admin)
        self.assertEqual(len(body["subjects"]), 10)
        self.assertEqual(body["subjects"][0], {"subject": "subject 05", "attempts": 2, "averageScore": 60.0})


# --------------------------------------------------------------------------- #
# Overview                                                                    #
# --------------------------------------------------------------------------- #


class OverviewTests(ReportsTestCase):
    def setUp(self):
        super().setUp()
        self.ann_at = now_ms() - timedelta(hours=3)
        practice(self.ann, 39.9, at=self.ann_at)
        practice(self.ben, 40, kind="interview", subject="Python")
        practice(self.cat, 90)
        practice(self.dan, 100)
        practice(self.admin, 5)  # not a student: ignored
        # Another tenant's numbers never count.
        practice(self.other_student, 1)
        foreign = make_test(self.other, self.other_cohort, "Foreign", starts_ago=timedelta(days=2))
        submit(foreign, self.other_student, score=1)

        self.t1 = make_test(self.inst, self.c1, "T1", starts_ago=timedelta(days=2))  # closed
        self.t2 = make_test(self.inst, self.b1, "T2", starts_ago=timedelta(minutes=10), duration=60)  # live
        make_test(self.inst, self.c3, "Nobody", starts_ago=timedelta(days=1))  # no students in C3
        self.ann_test_at = self.t1.starts_at + timedelta(minutes=10)
        submit(self.t1, self.ann, score=10, at=self.ann_test_at)  # 50%; Ben missed it
        submit(self.t2, self.dan, score=20, at=now_ms() - timedelta(minutes=1))  # 100%

    def test_institution_overview(self):
        body = self.get_ok(OVERVIEW, self.admin)
        self.assertIsNone(body["scope"])
        self.assertEqual(
            body["summary"],
            {
                "students": 5,
                "activeStudents": 4,
                "practiceAverage": round((39.9 + 90 + 100) / 3, 1),
                "interviewAverage": 40.0,
                "overallPracticeAverage": round((39.9 + 40 + 90 + 100) / 4, 1),
                "practiceSessions": 4,
                "testAverage": 75.0,
                "testSubmissions": 2,
                "testsMissed": 1,
                "completionRate": round(100 * 2 / 3, 1),
            },
        )
        self.assertEqual(
            [(d["band"], d["students"]) for d in body["distribution"]],
            [("Below 40%", 1), ("40–59%", 1), ("60–74%", 0), ("75–89%", 0), ("90% and up", 2)],
        )
        self.assertEqual(body["distribution"][-1]["max"], 100)
        self.assertEqual(body["distribution"][0]["min"], 0)
        self.assertEqual(body["unpractised"], 1)  # Eve

        self.assertEqual(
            [(g["level"], g["name"], g["students"], g["activeStudents"]) for g in body["groups"]],
            [("batch", "B1", 4, 4), ("batch", "B2", 0, 0)],
        )
        self.assertIsNone(body["groups"][1]["practiceAverage"])
        self.assertIsNone(body["groups"][1]["testAverage"])
        self.assertEqual(body["groups"][0]["testAverage"], 75.0)
        self.assertEqual(body["groups"][0]["id"], str(self.b1.pk))

        self.assertEqual(
            body["tests"],
            [
                {"id": str(self.t2.pk), "title": "T2", "startsAt": body["tests"][0]["startsAt"], "status": "live",
                 "audience": "B1", "students": 4, "submitted": 1, "averagePercentage": 100.0},
                {"id": str(self.t1.pk), "title": "T1", "startsAt": body["tests"][1]["startsAt"], "status": "closed",
                 "audience": "B1 · D1 · S1 · C1", "students": 2, "submitted": 1, "averagePercentage": 50.0},
            ],
        )

        rows = {r["name"]: r for r in body["students"]}
        self.assertEqual([r["name"] for r in body["students"]], ["Ann", "Ben", "Cat", "Dan", "Eve"])
        self.assertEqual(
            rows["Ann"],
            {
                "id": str(self.ann.pk), "name": "Ann", "email": self.ann.email,
                "placement": "B1 · D1 · S1 · C1", "practiceSessions": 1, "practiceAverage": 39.9,
                "testAverage": 50.0, "testsTaken": 1, "testsMissed": 0,
                "lastActiveAt": rows["Ann"]["lastActiveAt"],
            },
        )
        self.assertEqual(parse_datetime(rows["Ann"]["lastActiveAt"]), self.ann_at)  # practice is newer
        self.assertEqual((rows["Ben"]["testsMissed"], rows["Ben"]["testsTaken"]), (1, 0))
        self.assertEqual(rows["Dan"]["placement"], "B1 · D2 · S3 · C4")
        self.assertEqual(rows["Dan"]["testAverage"], 100.0)
        self.assertEqual(
            (rows["Eve"]["placement"], rows["Eve"]["practiceSessions"], rows["Eve"]["practiceAverage"],
             rows["Eve"]["lastActiveAt"], rows["Eve"]["testsMissed"]),
            (None, 0, None, None, 0),
        )
        self.assertNotIn("Outsider", rows)
        self.assertNotIn("Admin", rows)

    def test_last_active_uses_the_latest_test_submission(self):
        PracticeAttempt.objects.filter(user=self.ann).update(created_at=self.ann_test_at - timedelta(hours=1))
        body = self.get_ok(OVERVIEW, self.admin)
        ann = next(r for r in body["students"] if r["name"] == "Ann")
        self.assertEqual(parse_datetime(ann["lastActiveAt"]), self.ann_test_at)

    def test_other_tenant_overview_is_isolated(self):
        body = self.get_ok(OVERVIEW, self.other_admin)
        self.assertEqual(body["summary"]["students"], 1)
        self.assertEqual(body["summary"]["practiceSessions"], 1)
        self.assertEqual(body["summary"]["testSubmissions"], 1)
        self.assertEqual([t["title"] for t in body["tests"]], ["Foreign"])
        self.assertEqual([r["name"] for r in body["students"]], ["Outsider"])

    def test_completion_rate_is_none_without_tests(self):
        inst = make_institution()
        admin = make_user(inst, "admin")
        student = make_user(inst, "student", cohort=make_cohort(inst))
        practice(student, 70)
        body = self.get_ok(OVERVIEW, admin)
        self.assertIsNone(body["summary"]["completionRate"])
        self.assertIsNone(body["summary"]["testAverage"])
        self.assertEqual(body["tests"], [])
        self.assertEqual(body["summary"]["students"], 1)

    def test_section_scope(self):
        body = self.get_ok(OVERVIEW, self.educator, {"section": str(self.s1.pk)})
        self.assertEqual(body["scope"]["level"], "section")
        self.assertEqual(body["scope"]["id"], str(self.s1.pk))
        self.assertEqual(body["scope"]["label"], "B1 · D1 · S1")
        summary = body["summary"]
        self.assertEqual(summary["students"], 3)
        self.assertEqual(summary["practiceSessions"], 3)  # Dan's practice is outside
        self.assertEqual(summary["overallPracticeAverage"], round((39.9 + 40 + 90) / 3, 1))
        self.assertEqual(summary["testSubmissions"], 1)  # Dan's T2 submission is outside
        self.assertEqual(summary["testAverage"], 50.0)
        self.assertEqual(summary["testsMissed"], 1)
        self.assertEqual(
            [(g["level"], g["name"], g["students"]) for g in body["groups"]],
            [("cohort", "C1", 2), ("cohort", "C2", 1)],
        )
        tests = {t["title"]: t for t in body["tests"]}
        self.assertEqual(set(tests), {"T1", "T2"})
        self.assertEqual((tests["T2"]["students"], tests["T2"]["submitted"]), (3, 0))
        self.assertIsNone(tests["T2"]["averagePercentage"])
        self.assertEqual((tests["T1"]["students"], tests["T1"]["submitted"]), (2, 1))
        self.assertEqual([r["name"] for r in body["students"]], ["Ann", "Ben", "Cat"])

    def test_test_listed_for_scope_with_submissions_only(self):
        # Dan (C4) sits a test assigned to C1: it shows in a D2 scope through his submission.
        submit(self.t1, self.dan, score=5)
        body = self.get_ok(OVERVIEW, self.admin, {"department": str(self.d2.pk)})
        tests = {t["title"]: t for t in body["tests"]}
        self.assertEqual((tests["T1"]["students"], tests["T1"]["submitted"]), (0, 1))
        self.assertEqual(tests["T1"]["averagePercentage"], 25.0)

    def test_groups_are_one_level_below_the_scope(self):
        cases = [
            ({"batch": str(self.b1.pk)}, "batch", [("department", "D1", 3), ("department", "D2", 1)]),
            ({"batch": str(self.b2.pk)}, "batch", []),
            ({"department": str(self.d1.pk)}, "department", [("section", "S1", 3), ("section", "S2", 0)]),
            ({"section": str(self.s3.pk)}, "section", [("cohort", "C4", 1)]),
            ({"cohort": str(self.c1.pk)}, "cohort", []),
            # The deepest level given wins.
            ({"batch": str(self.b1.pk), "cohort": str(self.c1.pk)}, "cohort", []),
            ({"batch": str(self.b1.pk), "department": str(self.d1.pk)}, "department",
             [("section", "S1", 3), ("section", "S2", 0)]),
        ]
        for params, level, groups in cases:
            with self.subTest(params=params):
                body = self.get_ok(OVERVIEW, self.admin, params)
                self.assertEqual(body["scope"]["level"], level)
                self.assertEqual([(g["level"], g["name"], g["students"]) for g in body["groups"]], groups)

    def test_cohort_scope(self):
        body = self.get_ok(OVERVIEW, self.admin, {"cohort": str(self.c1.pk)})
        self.assertEqual(body["summary"]["students"], 2)
        self.assertEqual(body["summary"]["practiceSessions"], 2)
        self.assertEqual(body["unpractised"], 0)
        self.assertEqual(body["groups"], [])
        tests = {t["title"]: (t["students"], t["submitted"]) for t in body["tests"]}
        self.assertEqual(tests, {"T1": (2, 1), "T2": (2, 0)})

    def test_empty_scope(self):
        body = self.get_ok(OVERVIEW, self.admin, {"batch": str(self.b2.pk)})
        self.assertEqual(body["summary"]["students"], 0)
        self.assertEqual(body["summary"]["practiceSessions"], 0)
        self.assertIsNone(body["summary"]["completionRate"])
        self.assertEqual(body["tests"], [])
        self.assertEqual(body["students"], [])
        self.assertEqual(body["unpractised"], 0)

    def test_unknown_scope_is_rejected(self):
        cases = [
            ("batch", "abc"),
            ("department", str(ObjectId())),
            ("section", str(self.s1.pk) + "x"),
            ("cohort", str(self.other_cohort.pk)),  # another tenant's
            ("cohort", str(self.s1.pk)),  # an id of the wrong level
        ]
        for level, value in cases:
            with self.subTest(level=level, value=value):
                response = self.api_get(OVERVIEW, {level: value}, user=self.admin)
                self.assertStatus(response, 400)
                self.assertEqual(response.json()["message"], f"Unknown {level}")

    def test_blank_scope_params_are_ignored(self):
        body = self.get_ok(OVERVIEW, self.admin, {"cohort": "  ", "batch": ""})
        self.assertIsNone(body["scope"])
        self.assertEqual(body["summary"]["students"], 5)

    def test_tests_are_capped_at_twelve_newest_first(self):
        for n in range(14):
            make_test(self.inst, self.c2, f"Extra {n:02d}", starts_ago=timedelta(hours=3, minutes=n))
        body = self.get_ok(OVERVIEW, self.admin)
        self.assertEqual(len(body["tests"]), 12)
        self.assertEqual(body["tests"][0]["title"], "T2")
        self.assertEqual([t["title"] for t in body["tests"][1:]], [f"Extra {n:02d}" for n in range(11)])
        starts = [parse_datetime(t["startsAt"]) for t in body["tests"]]
        self.assertEqual(starts, sorted(starts, reverse=True))

    def test_attempt_left_open_is_counted(self):
        AssessmentAttempt.objects.create(
            assessment=self.t1, student=self.ben, order=["q1", "q2", "q3", "q4"],
            answers={"q1": "B", "q2": "B", "q3": "B", "q4": "B"},
        )
        body = self.get_ok(OVERVIEW, self.admin, {"cohort": str(self.c1.pk)})
        self.assertEqual(body["summary"]["testsMissed"], 0)
        self.assertEqual(body["summary"]["testSubmissions"], 2)
        self.assertEqual(body["summary"]["testAverage"], 75.0)  # 50 and 100
        self.assertEqual(body["summary"]["completionRate"], 100.0)

    def test_subjects(self):
        body = self.get_ok(OVERVIEW, self.admin)
        self.assertEqual(
            body["subjects"],
            [
                {"subject": "Java", "attempts": 3, "averageScore": round((39.9 + 90 + 100) / 3, 1)},
                {"subject": "Python", "attempts": 1, "averageScore": 40.0},
            ],
        )
