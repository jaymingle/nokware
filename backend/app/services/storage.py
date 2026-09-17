"""MinIO object storage. Ledger files and report photos live in separate buckets."""

import io
import mimetypes
from datetime import timedelta
from functools import lru_cache
from uuid import uuid4

from minio import Minio
from minio.error import S3Error

from app.config import get_settings

DEFAULT_URL_EXPIRY_SECONDS = 3600
# Set explicitly so the client never auto-detects it: detection needs
# s3:GetBucketLocation, which our access key's policy does not grant (every
# bucket operation then fails with AccessDenied). us-east-1 is MinIO's default.
MINIO_REGION = "us-east-1"


def _parse_endpoint(raw: str) -> tuple[str, bool]:
    """A bare hostname ("s3.example.com") means HTTPS."""
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


def _upload(bucket: str, file_bytes: bytes, filename: str, object_name: str | None = None) -> str:
    object_name = object_name or _object_name(filename)
    get_minio().put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=io.BytesIO(file_bytes),
        length=len(file_bytes),
        content_type=_content_type(filename),
    )
    return object_name


def upload_ledger_file(file_bytes: bytes, filename: str, object_name: str | None = None) -> str:
    """Returns the object name. Pass a stable object_name (e.g. a content hash) so repeated uploads of the same file
    land on the same object."""
    return _upload(get_settings().minio_ledger_bucket, file_bytes, filename, object_name)


def download_ledger_file(file_id: str) -> bytes:
    response = get_minio().get_object(bucket_name=get_settings().minio_ledger_bucket, object_name=file_id)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def ledger_file_exists(file_id: str) -> bool:
    try:
        get_minio().stat_object(bucket_name=get_settings().minio_ledger_bucket, object_name=file_id)
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            return False
        raise
    return True


def get_ledger_file_url(file_id: str, expires: int = DEFAULT_URL_EXPIRY_SECONDS) -> str:
    return get_minio().presigned_get_object(
        bucket_name=get_settings().minio_ledger_bucket,
        object_name=file_id,
        expires=timedelta(seconds=expires),
    )
