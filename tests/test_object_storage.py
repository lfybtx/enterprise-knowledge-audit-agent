import sys
import types

from app.services.object_storage import store_upload


def test_store_upload_falls_back_to_local_disk(tmp_path, monkeypatch):
    monkeypatch.delenv("MINIO_ENDPOINT", raising=False)

    stored = store_upload(
        content=b"hello",
        filename="policy.txt",
        object_id="doc-1",
        content_type="text/plain",
        fallback_dir=tmp_path,
    )

    assert stored.backend == "local"
    assert stored.source == "data/runtime/uploads/doc-1_policy.txt"
    assert (tmp_path / "doc-1_policy.txt").read_bytes() == b"hello"


def test_store_upload_writes_to_minio_when_configured(tmp_path, monkeypatch):
    calls = {}

    class FakeMinio:
        def __init__(self, endpoint, access_key, secret_key, secure):
            calls["client"] = {
                "endpoint": endpoint,
                "access_key": access_key,
                "secret_key": secret_key,
                "secure": secure,
            }

        def bucket_exists(self, bucket):
            calls["bucket_exists"] = bucket
            return False

        def make_bucket(self, bucket):
            calls["make_bucket"] = bucket

        def put_object(self, bucket, object_name, stream, length, content_type):
            calls["put_object"] = {
                "bucket": bucket,
                "object_name": object_name,
                "content": stream.read(),
                "length": length,
                "content_type": content_type,
            }

    fake_minio_module = types.ModuleType("minio")
    fake_minio_module.Minio = FakeMinio
    monkeypatch.setitem(sys.modules, "minio", fake_minio_module)
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("MINIO_SECRET_KEY", "minioadmin")
    monkeypatch.setenv("MINIO_BUCKET", "audit-documents")

    stored = store_upload(
        content=b"hello",
        filename="policy.txt",
        object_id="doc-1",
        content_type="text/plain",
        fallback_dir=tmp_path,
    )

    assert stored.backend == "minio"
    assert stored.source == "minio://audit-documents/uploads/doc-1/policy.txt"
    assert calls["make_bucket"] == "audit-documents"
    assert calls["put_object"]["content"] == b"hello"
