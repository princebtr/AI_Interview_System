"""Aggregations over practice results, shared by the admin, educator and student
dashboards. Done in Python over bounded querysets: simple, portable across
database backends, and plenty fast at institution scale."""
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from institutions.models import LEVELS

from .models import PracticeAttempt

ANALYTICS_DAYS = 90  # window for "how is this group/subject doing" numbers
PLACEMENT_IDS = tuple(f"{level}_id" for level in LEVELS)


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


def group_stats(institution):
    """{(level, pk): {studentCount, activated, attempts, practice30Days, averageScore}}
    for every batch, department, section and cohort that has students. Practice
    covers ANALYTICS_DAYS. One pass over the students and one over the attempts."""
    stats = defaultdict(lambda: {"studentCount": 0, "activated": 0, "attempts": 0, "practice30Days": 0, "_scores": []})

    groups_of = {}
    students = User.objects.filter(institution=institution, role="student", cohort__isnull=False)
    for pk, *ids, last_login in students.values_list(*("pk", *PLACEMENT_IDS, "last_login")):
        keys = [(level, group_id) for level, group_id in zip(LEVELS, ids) if group_id]
        groups_of[pk] = keys
        for key in keys:
            stats[key]["studentCount"] += 1
            stats[key]["activated"] += last_login is not None

    recent_cutoff = since(30)
    attempts = PracticeAttempt.objects.filter(
        institution=institution, created_at__gte=since(ANALYTICS_DAYS)
    ).values_list("user_id", "score", "created_at")
    for user_id, score, created_at in attempts:
        for key in groups_of.get(user_id, ()):
            entry = stats[key]
            entry["attempts"] += 1
            entry["_scores"].append(score)
            entry["practice30Days"] += created_at >= recent_cutoff

    for entry in stats.values():
        entry["averageScore"] = average(entry.pop("_scores"))
    return dict(stats)


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
