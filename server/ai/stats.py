"""Aggregations over practice results, shared by the admin, educator and student
dashboards. Done in Python over bounded querysets: simple, portable across
database backends, and plenty fast at institution scale."""
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from institutions.models import Cohort

from .models import PracticeAttempt

ANALYTICS_DAYS = 90  # window for "how is this cohort/subject doing" numbers


def average(values):
    values = list(values)
    return round(sum(values) / len(values), 1) if values else None


def since(days):
    return timezone.now() - timedelta(days=days)


def daily_counts(timestamps, days=14):
    """[{date, count}] for the last `days` days, oldest first."""
    today = timezone.localdate()
    buckets = {today - timedelta(days=i): 0 for i in range(days)}
    for ts in timestamps:
        day = timezone.localtime(ts).date()
        if day in buckets:
            buckets[day] += 1
    return [{"date": day.isoformat(), "count": buckets[day]} for day in sorted(buckets)]


def subject_breakdown(rows, limit=None):
    """rows: (subject, subject_key, score), newest first. The newest spelling
    of a subject is the one shown."""
    scores, names = defaultdict(list), {}
    for subject, key, score in rows:
        scores[key].append(score)
        names.setdefault(key, subject)
    result = sorted(
        (
            {"subject": names[key], "attempts": len(values), "averageScore": average(values)}
            for key, values in scores.items()
        ),
        key=lambda s: (-s["attempts"], s["subject"].casefold()),
    )
    return result[:limit] if limit else result


def streak_days(timestamps):
    """Consecutive days with practice, ending today (or yesterday)."""
    days = {timezone.localtime(ts).date() for ts in timestamps}
    day = timezone.localdate()
    if day not in days:
        day -= timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def cohort_stats(institution, cohort_ids=None):
    """Per-cohort student counts, sign-ins and practice over ANALYTICS_DAYS."""
    cohorts = Cohort.objects.filter(institution=institution).order_by("name_key")
    if cohort_ids is not None:
        cohorts = cohorts.filter(pk__in=cohort_ids)
    stats = {
        c.pk: {
            "id": str(c.pk),
            "name": c.name,
            "createdAt": c.created_at,
            "studentCount": 0,
            "activated": 0,
            "attempts": 0,
            "practice30Days": 0,
            "_scores": [],
        }
        for c in cohorts
    }

    cohort_of = {}
    students = User.objects.filter(institution=institution, role="student", cohort__isnull=False)
    for pk, cohort_id, last_login in students.values_list("pk", "cohort_id", "last_login"):
        if cohort_id in stats:
            cohort_of[pk] = cohort_id
            stats[cohort_id]["studentCount"] += 1
            stats[cohort_id]["activated"] += last_login is not None

    recent_cutoff = since(30)
    attempts = PracticeAttempt.objects.filter(
        institution=institution, created_at__gte=since(ANALYTICS_DAYS)
    ).values_list("user_id", "score", "created_at")
    for user_id, score, created_at in attempts:
        cohort_id = cohort_of.get(user_id)
        if cohort_id is None:
            continue
        entry = stats[cohort_id]
        entry["attempts"] += 1
        entry["_scores"].append(score)
        entry["practice30Days"] += created_at >= recent_cutoff

    result = []
    for entry in stats.values():
        entry["averageScore"] = average(entry.pop("_scores"))
        result.append(entry)
    return result


def student_stats(institution, student_ids):
    """{user_id: {attempts, averageScore, lastPracticeAt}} over ANALYTICS_DAYS."""
    stats = {pk: {"attempts": 0, "averageScore": None, "lastPracticeAt": None, "_s": []} for pk in student_ids}
    if not stats:
        return {}
    attempts = PracticeAttempt.objects.filter(
        institution=institution, user_id__in=list(stats), created_at__gte=since(ANALYTICS_DAYS)
    ).values_list("user_id", "score", "created_at")
    for user_id, score, created_at in attempts:
        entry = stats[user_id]
        entry["attempts"] += 1
        entry["_s"].append(score)
        if entry["lastPracticeAt"] is None or created_at > entry["lastPracticeAt"]:
            entry["lastPracticeAt"] = created_at
    for entry in stats.values():
        entry["averageScore"] = average(entry.pop("_s"))
    return stats


def student_subject_rows(institution, days=ANALYTICS_DAYS):
    """(subject, subject_key, score) for every attempt in the window, newest first.
    Practice endpoints are student-only, so these are all students' attempts."""
    return (
        PracticeAttempt.objects.filter(institution=institution, created_at__gte=since(days))
        .order_by("-created_at")
        .values_list("subject", "subject_key", "score")
    )
