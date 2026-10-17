"""Measure the proctoring pipeline on labelled images.

Labels are a JSON list; each item names an image (relative to the labels file,
or --images) and any of:
    {"file": "a.jpg", "people": 1, "phone": false}
"people" is the number of people in view, "phone" whether a phone is visible.
Reports per-frame precision, recall and false-positive rate for absence,
multiple people and phones, plus latency. These are single-frame numbers: in a
test, incidents also need several matching frames (settings.PROCTORING).
"""
import json
import statistics
import time
from pathlib import Path

import cv2
from django.core.management.base import BaseCommand, CommandError

from ai import vision


def rates(pairs):
    """pairs: [(truth, predicted)] booleans."""
    tp = sum(t and p for t, p in pairs)
    fp = sum(p and not t for t, p in pairs)
    fn = sum(t and not p for t, p in pairs)
    tn = sum(not t and not p for t, p in pairs)
    div = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
    return {
        "positives": tp + fn,
        "negatives": fp + tn,
        "precision": div(tp, tp + fp),
        "recall": div(tp, tp + fn),
        "falsePositiveRate": div(fp, fp + tn),
    }


class Command(BaseCommand):
    help = "Precision, recall, false-positive rate and latency of camera checks on labelled images."

    def add_arguments(self, parser):
        parser.add_argument("labels", help="JSON list of {file, people?, phone?}")
        parser.add_argument("--images", help="Folder the files are in (default: the labels file's folder)")
        parser.add_argument("--json", action="store_true", help="Print the report as JSON")

    def handle(self, *args, labels, images=None, json=False, **options):
        import json as jsonlib

        if not vision.available():
            raise CommandError("Detection models missing: run manage.py fetch_proctoring_models")
        items = jsonlib.loads(Path(labels).read_text())
        folder = Path(images or Path(labels).parent)

        vision.analyse(cv2.imread(str(folder / items[0]["file"])))  # load the models before timing
        absent, multiple, phone, suspected, latencies, people_ok = [], [], [], [], [], {}
        for item in items:
            frame = cv2.imread(str(folder / item["file"]))
            if frame is None:
                raise CommandError(f"Can't read {item['file']}")
            started = time.perf_counter()
            result = vision.analyse(frame)
            latencies.append((time.perf_counter() - started) * 1000)
            if "people" in item:
                truth = item["people"]
                absent.append((truth == 0, result["people"] == 0))
                multiple.append((truth >= 2, result["people"] >= 2))
                bucket = min(truth, 2)
                hits, total = people_ok.get(bucket, (0, 0))
                people_ok[bucket] = (hits + (min(result["people"], 2) == bucket), total + 1)
            if "phone" in item:
                phone.append((bool(item["phone"]), result["phone"]))
                suspected.append((bool(item["phone"]), result["phoneSuspected"]))

        latencies.sort()
        report = {
            "images": len(items),
            "absence": rates(absent) if absent else None,
            "multiplePeople": rates(multiple) if multiple else None,
            "peopleCountAccuracy": {
                {0: "nobody", 1: "one", 2: "several"}[k]: round(h / t, 3) for k, (h, t) in sorted(people_ok.items())
            },
            "phoneDetected": rates(phone) if phone else None,
            "phoneSuspected": rates(suspected) if suspected else None,
            "latencyMs": {
                "median": round(statistics.median(latencies)),
                "p95": round(latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]),
            },
        }
        if json:
            self.stdout.write(jsonlib.dumps(report, indent=2))
            return
        for name, value in report.items():
            self.stdout.write(f"{name}: {value}")
