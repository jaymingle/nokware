"""The images a creator shows with their petition.

Every image goes through the same cleaning a report's photo does — decoded and re-encoded from its pixels alone, so
no EXIF, and with it no GPS position, survives. A petition is public, and a photo of the drain outside someone's
house should not also carry the house's coordinates.

They are stored in the same private bucket and shown through short-lived links, so an image can stop being served
the moment its petition is removed.
"""

import io
import uuid

from app.config import get_settings
from app.services.report_photos import clean_photos, photo_link
from app.services.storage import get_minio

IMAGES_PREFIX = "petitions"


def store_images(images: list[bytes], limit: int) -> list[str]:
    """The stored object names, in the order they were given. The folder is a fresh random one rather than the
    petition's number: a petition has no number until it exists, and an image is never addressed by guesswork."""
    if not images:
        return []
    folder = uuid.uuid4().hex
    bucket = get_settings().minio_photos_bucket
    names = []
    for position, image in enumerate(clean_photos(images, limit), start=1):
        name = f"{IMAGES_PREFIX}/{folder}/{position:02d}-{uuid.uuid4().hex[:12]}.jpg"
        get_minio().put_object(bucket, name, io.BytesIO(image.data), len(image.data), content_type="image/jpeg")
        names.append(name)
    return names


def image_links(object_names: list[str] | None) -> list[str]:
    return [photo_link(name) for name in object_names or []]
