"""Report numbers over a date window: one student's, or a group of students'.

Covers practice (practice tests and AI interview answers, scored 0-100) and
scheduled tests (as a percentage of the test's marks). Done in Python over
bounded querysets, like ai.stats: simple, and plenty fast at institution scale.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.utils import timezone

from accounts.models import User
from ai import stats
from ai.models import PracticeAttempt
from assessments import sitting
from assessments.models import Assessment, AssessmentAttempt
from institutions import structure
from institutions.models import LEVELS, MODELS

RANGES = (30, 90, 180, 365)
DEFAULT_RANGE = 90
# Students are banded by their average practice score.
BANDS = [(0, 40, "Below 40%"), (40, 60, "40–59%"), (60, 75, "60–74%"), (75, 90, "75–89%"), (90, 101, "90% and up")]
TOP_SUBJECTS = 10
OVERVIEW_TESTS = 12
PLACEMENT_IDS = tuple(f"{level}_id" for level in LEVELS)

average = stats.average


def window(days):
    """(start, now): from midnight `days - 1` days ago (local time) until now."""
    now = timezone.now()
    first_day = timezone.localdate(now) - timedelta(days=days - 1)
    return timezone.make_aware(datetime.combine(first_day, time.min)), now


def week_of(ts):
    """The Monday of the (local) week `ts` falls in."""
    day = timezone.localtime(ts).date()
    return day - timedelta(days=day.weekday())


def weeks_between(start, now):
    week, last, result = week_of(start), week_of(now), []
    while week <= last:
        result.append(week)
        week += timedelta(days=7)
    return result


def _in_audience(test, placement):
    """Whether a student placed at `placement` ({level: id}) is in the test's audience."""
    level, group_id = test.audience_key()
    return placement.get(level) == group_id


def load_tests(institution, start, now, student_ids=None):
    """Scheduled tests that started in the window, and their submitted results as
    [(test id, student id, submitted_at, percentage)] (optionally for some students)."""
    tests = list(
        Assessment.objects.filter(institution=institution, starts_at__gte=start, starts_at__lte=now)
        .select_related(*Assessment.AUDIENCE_FIELDS)
        .order_by("starts_at")
    )
    sitting.finalize_closed(tests)  # count attempts left open when time ran out
    marks = {t.pk: t.total_marks for t in tests}
    attempts = AssessmentAttempt.objects.filter(assessment_id__in=list(marks), submitted_at__isnull=False)
    if student_ids is not None:
        attempts = attempts.filter(student_id__in=list(student_ids))
    results = []
    for test_id, student_id, submitted_at, score, raw, penalty in attempts.values_list(
        "assessment_id", "student_id", "submitted_at", "score", "raw_score", "total_penalty"
    ):
        if not marks[test_id]:
            continue
        final = score if score is not None else max(0.0, (raw or 0) - (penalty or 0))
        results.append((test_id, student_id, submitted_at, round(final / marks[test_id] * 100, 1)))
    return tests, results


def _trend(weeks, practice, test_results, active=None):
    """Weekly points: average practice-test, interview and scheduled-test scores,
    practice sessions and (for groups) active students."""
    buckets = {
        week: {"practice": [], "interview": [], "tests": [], "sessions": 0, "active": set()} for week in weeks
    }
    for user_id, kind, score, ts in practice:
        bucket = buckets.get(week_of(ts))
        if bucket:
            bucket["practice" if kind == "mcq" else "interview"].append(score)
            bucket["sessions"] += 1
            bucket["active"].add(user_id)
    for user_id, submitted_at, percentage in test_results:
        bucket = buckets.get(week_of(submitted_at))
        if bucket:
            bucket["tests"].append(percentage)
            bucket["active"].add(user_id)
    return [
        {
            "week": week.isoformat(),
            "practice": average(b["practice"]),
            "interview": average(b["interview"]),
            "tests": average(b["tests"]),
            "sessions": b["sessions"],
            **({"activeStudents": len(b["active"])} if active else {}),
        }
        for week, b in buckets.items()
    ]


# --------------------------------------------------------------------------- #
# One student                                                                  #
# --------------------------------------------------------------------------- #


def student_report(student, days):
    start, now = window(days)
    attempts = PracticeAttempt.objects.filter(user=student, created_at__gte=start).order_by("-created_at")
    practice = list(attempts.values_list("kind", "subject", "subject_key", "score", "created_at"))
    tests, results = load_tests(student.institution, start, now)

    by_test = defaultdict(list)
    for test_id, _, _, percentage in results:
        by_test[test_id].append(percentage)
    mine = {test_id: (at, pct) for test_id, student_id, at, pct in results if student_id == student.pk}
    placement = {level: getattr(student, f"{level}_id") for level in LEVELS}

    test_rows = []
    for test in tests:
        taken = mine.get(test.pk)
        if taken is None and not (student.cohort_id and _in_audience(test, placement)):
            continue
        status = "submitted" if taken else ("missed" if test.ends_at <= now else "open")
        test_rows.append(
            {
                "id": str(test.pk),
                "title": test.title,
                "subject": test.subject,
                "startsAt": test.starts_at,
                "status": status,
                "percentage": taken[1] if taken else None,
                "groupAverage": average(by_test[test.pk]),
            }
        )

    # The same numbers for the rest of the student's cohort, to compare against.
    mates = (
        set(
            User.objects.filter(cohort_id=student.cohort_id, role="student")
            .exclude(pk=student.pk)
            .values_list("pk", flat=True)
        )
        if student.cohort_id
        else set()
    )
    cohort_practice = (
        PracticeAttempt.objects.filter(user_id__in=list(mates), created_at__gte=start).values_list("score", flat=True)
        if mates
        else []
    )

    mcq = [score for kind, _, _, score, _ in practice if kind == "mcq"]
    interview = [score for kind, _, _, score, _ in practice if kind != "mcq"]
    my_tests = [pct for _, pct in mine.values()]
    return {
        "range": {"days": days, "from": start, "to": now},
        "summary": {
            "practiceAverage": average(mcq),
            "practiceTests": len(mcq),
            "interviewAverage": average(interview),
            "interviewAnswers": len(interview),
            "overallPracticeAverage": average(mcq + interview),
            "testAverage": average(my_tests),
            "testsTaken": len(my_tests),
            "testsMissed": sum(r["status"] == "missed" for r in test_rows),
            "streakDays": stats.streak_days(ts for *_, ts in practice),
            "cohortPracticeAverage": average(cohort_practice),
            "cohortTestAverage": average(pct for _, sid, _, pct in results if sid in mates),
        },
        "trend": _trend(
            weeks_between(start, now),
            [(student.pk, kind, score, ts) for kind, _, _, score, ts in practice],
            [(student.pk, at, pct) for at, pct in mine.values()],
        ),
        "subjects": stats.subject_breakdown(((s, k, score) for _, s, k, score, _ in practice), limit=TOP_SUBJECTS),
        "tests": test_rows[::-1],  # newest first
        "recent": [a.to_dict() for a in attempts[:10]],
    }


# --------------------------------------------------------------------------- #
# A group of students                                                          #
# --------------------------------------------------------------------------- #


def _labels(institution):
    """{(level, pk): name} for every group of the institution (four queries)."""
    return {
        (level, pk): name
        for level in LEVELS
        for pk, name in MODELS[level].objects.filter(institution=institution).values_list("pk", "name")
    }


def overview(institution, students, scope, days):
    """Reports for the students in `students` (a User queryset), who are the
    whole institution or the members of `scope` (a group node)."""
    start, now = window(days)
    rows = list(
        students.filter(role="student").values_list("pk", "name", "email", *PLACEMENT_IDS).order_by("name")
    )
    ids = [row[0] for row in rows]
    placements = {row[0]: dict(zip(LEVELS, row[3:])) for row in rows}

    practice = PracticeAttempt.objects.filter(institution=institution, created_at__gte=start)
    if scope is not None:
        practice = practice.filter(user_id__in=ids)
    practice = [
        p for p in practice.values_list("user_id", "kind", "subject", "subject_key", "score", "created_at")
        if p[0] in placements
    ]
    tests, results = load_tests(institution, start, now, ids if scope is not None else None)
    results = [r for r in results if r[1] in placements]

    # Per student.
    per = {pk: {"scores": [], "sessions": 0, "tests": [], "missed": 0, "last": None} for pk in ids}
    for user_id, _, _, _, score, ts in practice:
        entry = per[user_id]
        entry["scores"].append(score)
        entry["sessions"] += 1
        entry["last"] = max(entry["last"] or ts, ts)
    taken = set()
    for test_id, user_id, at, pct in results:
        entry = per[user_id]
        entry["tests"].append(pct)
        entry["last"] = max(entry["last"] or at, at)
        taken.add((test_id, user_id))
    expected = defaultdict(int)  # test id -> students in scope it was assigned to
    for test in tests:
        closed = test.ends_at <= now
        for pk, placement in placements.items():
            if placement["cohort"] and _in_audience(test, placement):
                expected[test.pk] += 1
                if closed and (test.pk, pk) not in taken:
                    per[pk]["missed"] += 1

    labels = _labels(institution)
    student_rows = [
        {
            "id": str(pk),
            "name": name,
            "email": email,
            "placement": " · ".join(labels.get((l, placements[pk][l]), "") for l in LEVELS if placements[pk][l])
            or None,
            "practiceSessions": per[pk]["sessions"],
            "practiceAverage": average(per[pk]["scores"]),
            "testAverage": average(per[pk]["tests"]),
            "testsTaken": len(per[pk]["tests"]),
            "testsMissed": per[pk]["missed"],
            "lastActiveAt": per[pk]["last"],
        }
        for pk, name, email, *_ in rows
    ]

    # Distribution of students by average practice score.
    averages = [average(e["scores"]) for e in per.values() if e["scores"]]
    distribution = [
        {"band": label, "min": low, "max": min(high, 100), "students": sum(low <= a < high for a in averages)}
        for low, high, label in BANDS
    ]

    # One level down from the scope: batches of the institution, departments of a batch...
    child_level = LEVELS[0] if scope is None else structure.CHILD_LEVEL.get(scope.LEVEL)
    groups = []
    if child_level:
        children = (
            MODELS[child_level].objects.filter(institution=institution)
            if scope is None
            else getattr(scope, structure.CHILDREN[scope.LEVEL]).all()
        )
        members = defaultdict(list)
        for pk, placement in placements.items():
            members[placement[child_level]].append(pk)
        for child in children:
            pks = members.get(child.pk, [])
            groups.append(
                {
                    "level": child_level,
                    "id": str(child.pk),
                    "name": child.name,
                    "students": len(pks),
                    "activeStudents": sum(1 for pk in pks if per[pk]["sessions"] or per[pk]["tests"]),
                    "practiceAverage": average(s for pk in pks for s in per[pk]["scores"]),
                    "testAverage": average(t for pk in pks for t in per[pk]["tests"]),
                }
            )

    by_test = defaultdict(list)
    for test_id, _, _, pct in results:
        by_test[test_id].append(pct)
    test_rows = [
        {
            "id": str(t.pk),
            "title": t.title,
            "startsAt": t.starts_at,
            "status": t.status(now),
            "audience": t.audience_dict()["label"],
            "students": expected[t.pk],
            "submitted": len(by_test[t.pk]),
            "averagePercentage": average(by_test[t.pk]),
        }
        for t in sorted(tests, key=lambda t: t.starts_at, reverse=True)
        if expected[t.pk] or by_test[t.pk]
    ][:OVERVIEW_TESTS]

    all_scores = [p[4] for p in practice]
    all_tests = [r[3] for r in results]
    missed = sum(e["missed"] for e in per.values())
    return {
        "range": {"days": days, "from": start, "to": now},
        "scope": scope.node_dict() if scope is not None else None,
        "summary": {
            "students": len(ids),
            "activeStudents": sum(1 for e in per.values() if e["sessions"] or e["tests"]),
            "practiceAverage": average(p[4] for p in practice if p[1] == "mcq"),
            "interviewAverage": average(p[4] for p in practice if p[1] != "mcq"),
            "overallPracticeAverage": average(all_scores),
            "practiceSessions": len(practice),
            "testAverage": average(all_tests),
            "testSubmissions": len(all_tests),
            "testsMissed": missed,
            "completionRate": round(100 * len(all_tests) / (len(all_tests) + missed), 1)
            if all_tests or missed
            else None,
        },
        "trend": _trend(
            weeks_between(start, now),
            [(u, kind, score, ts) for u, kind, _, _, score, ts in practice],
            [(u, at, pct) for _, u, at, pct in results],
            active=True,
        ),
        "distribution": distribution,
        "unpractised": sum(1 for e in per.values() if not e["scores"]),
        "groups": groups,
        "subjects": stats.subject_breakdown(
            ((s, k, score) for _, _, s, k, score, _ in sorted(practice, key=lambda p: p[5], reverse=True)),
            limit=TOP_SUBJECTS,
        ),
        "tests": test_rows,
        "students": student_rows,
    }
