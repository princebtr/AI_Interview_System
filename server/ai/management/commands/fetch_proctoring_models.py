"""Download the proctoring models into server/models/ (checksums verified)."""
import hashlib
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

MODELS = {
    "yolo11m.pt": (
        "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt",
        "d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95",
    ),
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Download the proctoring models (YOLO11m objects, YuNet faces)."

    def handle(self, *args, **options):
        wanted = {Path(settings.PROCTORING["OBJECT_MODEL"]), Path(settings.PROCTORING["FACE_MODEL"])}
        for path in sorted(wanted):
            if path.name not in MODELS:
                self.stdout.write(f"{path.name}: not a known model, place it in {path.parent} yourself")
                continue
            url, checksum = MODELS[path.name]
            if path.exists() and sha256(path) == checksum:
                self.stdout.write(f"{path.name}: already present")
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(path.suffix + ".part")
            self.stdout.write(f"{path.name}: downloading {url}")
            urllib.request.urlretrieve(url, partial)
            if sha256(partial) != checksum:
                partial.unlink()
                raise CommandError(f"{path.name}: checksum mismatch, download discarded")
            partial.replace(path)
            self.stdout.write(self.style.SUCCESS(f"{path.name}: saved to {path}"))
