from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ObjectStorageError(RuntimeError):
    """Raised when an uploaded object cannot be stored."""


@dataclass(frozen=True)
class StoredObject:
    source: str
    backend: str
    bucket: Optional[str] = None
    object_name: Optional[str] = None
    local_path: Optional[str] = None


@dataclass(frozen=True)
class ObjectStorageSettings:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    secure: bool

    @classmethod
    def from_environment(cls) -> Optional["ObjectStorageSettings"]:
        endpoint = os.getenv("MINIO_ENDPOINT", "").strip()
        access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
        secret_key = os.getenv("MINIO_SECRET_KEY", "").strip()
        bucket = os.getenv("MINIO_BUCKET", "audit-documents").strip()
        if not endpoint:
            return None
        if not access_key or not secret_key:
            raise ObjectStorageError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY are required when MINIO_ENDPOINT is set")
        return cls(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket or "audit-documents",
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )


def store_upload(
    *,
    content: bytes,
    filename: str,
    object_id: str,
    content_type: str,
    fallback_dir: Path,
) -> StoredObject:
    settings = ObjectStorageSettings.from_environment()
    object_name = f"uploads/{object_id}/{filename}"
    if settings is not None:
        try:
            return _store_in_minio(settings, object_name, content, content_type)
        except ObjectStorageError:
            raise
        except Exception as error:
            raise ObjectStorageError(f"Unable to store upload in MinIO: {error}") from error
    return _store_on_disk(content, filename, object_id, fallback_dir)


def _store_in_minio(
    settings: ObjectStorageSettings,
    object_name: str,
    content: bytes,
    content_type: str,
) -> StoredObject:
    try:
        from io import BytesIO

        from minio import Minio
    except ImportError as error:
        raise ObjectStorageError("MinIO support requires the minio package") from error

    client = Minio(
        settings.endpoint,
        access_key=settings.access_key,
        secret_key=settings.secret_key,
        secure=settings.secure,
    )
    if not client.bucket_exists(settings.bucket):
        client.make_bucket(settings.bucket)
    client.put_object(
        settings.bucket,
        object_name,
        BytesIO(content),
        length=len(content),
        content_type=content_type or "application/octet-stream",
    )
    return StoredObject(
        source=f"minio://{settings.bucket}/{object_name}",
        backend="minio",
        bucket=settings.bucket,
        object_name=object_name,
    )


def _store_on_disk(content: bytes, filename: str, object_id: str, fallback_dir: Path) -> StoredObject:
    fallback_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{object_id}_{filename}"
    stored_path = fallback_dir / stored_name
    stored_path.write_bytes(content)
    return StoredObject(
        source=f"data/runtime/uploads/{stored_name}",
        backend="local",
        local_path=str(stored_path),
    )
