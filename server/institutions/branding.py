"""Logo uploads: validate, normalise and store institution logos."""
import hashlib
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from config.http import BadRequest

MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_SOURCE_PIXELS = 25_000_000  # reject decompression bombs before decoding
LOGO_SIZE = 256  # longest side of the stored image (crisp at 2x in the sidebar)
ACCEPTED_FORMATS = {"PNG", "JPEG", "WEBP"}


def process_logo(upload):
    """Return (png_bytes, version) for an uploaded image.

    Re-encoding to a small PNG strips metadata and anything appended to the
    file, and keeps every logo cheap to serve. SVG isn't accepted: it can carry
    scripts.
    """
    if upload is None:
        raise BadRequest("Choose an image to upload")
    if upload.size > MAX_LOGO_BYTES:
        raise BadRequest("The logo must be 2 MB or smaller")
    data = upload.read()
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ACCEPTED_FORMATS:
                raise BadRequest("Upload a PNG, JPG or WebP image")
            width, height = source.size
            if width * height > MAX_SOURCE_PIXELS:
                raise BadRequest("That image is too large. Use one under 5000 × 5000 pixels.")
            image = ImageOps.exif_transpose(source).convert("RGBA")
    except BadRequest:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise BadRequest("That file isn't a valid image")

    image.thumbnail((LOGO_SIZE, LOGO_SIZE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    png = out.getvalue()
    return png, hashlib.sha256(png).hexdigest()[:12]
