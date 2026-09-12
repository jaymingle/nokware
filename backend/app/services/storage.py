"""MinIO object storage client and typed helpers.

Wraps a cached ``minio.Minio`` client. Ledger files and report photos live in
separate buckets (configured via settings). Object names are prefixed with a
random UUID to avoid collisions while preserving the original filename.
"""

import io
import mimetypes
from datetime import timedelta
from functools import lru_cache
from uuid import uuid4

from minio import Minio

from app.config import get_settings

MAX_PHOTOS = 10
DEFAULT_URL_EXPIRY_SECONDS = 3600
# Set explicitly so the client never auto-detects it: detection needs
# s3:GetBucketLocation, which our access key's policy does not grant (every
# bucket operation then fails with AccessDenied). us-east-1 is MinIO's default.
MINIO_REGION = "us-east-1"


def _parse_endpoint(raw: str) -> tuple[str, bool]:
    """Split an endpoint into (host[:port], secure) as minio.Minio expects.

    Accepts a bare hostname ("s3.example.com", HTTPS on 443) or a URL with an
    http:// or https:// scheme. Bare hostnames default to secure=True.
    """
    if raw.startswith("https://"):
        return raw[len("https://"):].rstrip("/"), True
    if raw.startswith("http://"):
        return raw[len("http://"):].rstrip("/"), False
    return raw.rstrip("/"), True


@lru_cache
def get_minio() -> Minio:
    settings = get_settings()
    host, secure = _parse_endpoint(settings.minio_endpoint)
    return Minio(
        endpoint=host,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
        region=MINIO_REGION,
    )


def _object_name(filename: str) -> str:
    return f"{uuid4().hex}-{filename}"


def _content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _upload(bucket: str, file_bytes: bytes, filename: str) -> str:
    object_name = _object_name(filename)
    get_minio().put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=io.BytesIO(file_bytes),
        length=len(file_bytes),
        content_type=_content_type(filename),
    )
    return object_name


def upload_ledger_file(file_bytes: bytes, filename: str) -> str:
    """Upload a ledger document; returns its object id (name in the bucket)."""
    settings = get_settings()
    return _upload(settings.minio_ledger_bucket, file_bytes, filename)


def upload_report_photos(files: list[bytes], filenames: list[str]) -> list[str]:
    """Upload up to ``MAX_PHOTOS`` report photos; returns their object ids."""
    if len(files) != len(filenames):
        raise ValueError("files and filenames must be the same length")
    if len(files) > MAX_PHOTOS:
        raise ValueError(f"at most {MAX_PHOTOS} photos may be uploaded at once")
    settings = get_settings()
    return [
        _upload(settings.minio_photos_bucket, data, name)
        for data, name in zip(files, filenames)
    ]


def get_ledger_file_url(
    file_id: str, expires: int = DEFAULT_URL_EXPIRY_SECONDS
) -> str:
    """Return a presigned GET URL for a ledger file, valid ``expires`` seconds."""
    settings = get_settings()
    return get_minio().presigned_get_object(
        bucket_name=settings.minio_ledger_bucket,
        object_name=file_id,
        expires=timedelta(seconds=expires),
    )
