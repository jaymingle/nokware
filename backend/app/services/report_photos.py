"""Photos attached to a citizen report: checked, cleaned and stored privately.

Every photo is decoded and re-encoded as a fresh JPEG made from its pixels
alone. Nothing of the original file survives: no EXIF (phones write the GPS
position there, which would give away a home address that the report itself
only locates by ward), no XMP, no thumbnails, no comments. The photo is turned
upright first, since that turn is otherwise stored as metadata.

Photos are stored in their own private bucket and only ever shown to a case's
recipients through short-lived links.
"""

import io
import uuid
from dataclasses import dataclass
from datetime import timedelta

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings
from app.services.citizen_reports import MAX_PHOTOS
from app.services.storage import get_minio

MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_EDGE = 2048  # long side after resizing: plenty to see a pothole, far smaller to store
MAX_PIXELS = 40_000_000  # refuse decompression bombs well before Pillow's own limit
ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}
JPEG_QUALITY = 85
PHOTO_LINK_SECONDS = 600


class PhotoRejected(ValueError):
    """A photo can't be accepted; the message is safe to show the citizen."""


@dataclass(frozen=True)
class CleanPhoto:
    data: bytes
    width: int
    height: int


def _open(data: bytes, position: int) -> Image.Image:
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoRejected(f"Photo {position} is larger than 10 MB.")
    try:
        image = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError) as error:
        raise PhotoRejected(f"Photo {position} isn't a JPEG, PNG or WebP image.") from error
    if image.format not in ACCEPTED_FORMATS:
        raise PhotoRejected(f"Photo {position} isn't a JPEG, PNG or WebP image.")
    if image.width * image.height > MAX_PIXELS:
        raise PhotoRejected(f"Photo {position} has too many pixels.")
    return image


def clean_photo(data: bytes, position: int = 1) -> CleanPhoto:
    with _open(data, position) as image:
        try:
            upright = ImageOps.exif_transpose(image).convert("RGB")
        except (OSError, ValueError) as error:
            raise PhotoRejected(f"Photo {position} couldn't be read.") from error
    upright.thumbnail((MAX_EDGE, MAX_EDGE))
    # A new image from raw pixels carries no info dict: no EXIF, XMP, ICC or comments.
    pixels_only = Image.frombytes("RGB", upright.size, upright.tobytes())
    out = io.BytesIO()
    pixels_only.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return CleanPhoto(out.getvalue(), pixels_only.width, pixels_only.height)


def clean_photos(photos: list[bytes]) -> list[CleanPhoto]:
    if len(photos) > MAX_PHOTOS:
        raise PhotoRejected(f"Attach at most {MAX_PHOTOS} photos.")
    return [clean_photo(data, position) for position, data in enumerate(photos, start=1)]


def store_photos(case_id: str, photos: list[CleanPhoto]) -> list[str]:
    bucket = get_settings().minio_photos_bucket
    names = []
    for position, photo in enumerate(photos, start=1):
        name = f"reports/{case_id}/{position:02d}-{uuid.uuid4().hex[:12]}.jpg"
        get_minio().put_object(bucket, name, io.BytesIO(photo.data), len(photo.data), content_type="image/jpeg")
        names.append(name)
    return names


def photo_link(object_name: str) -> str:
    return get_minio().presigned_get_object(
        get_settings().minio_photos_bucket, object_name, expires=timedelta(seconds=PHOTO_LINK_SECONDS)
    )
