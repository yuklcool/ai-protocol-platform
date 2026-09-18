from __future__ import annotations

from io import BytesIO

import pytest

from object_storage.factory import _reset_object_storage_for_tests, get_object_storage
from object_storage.local import StoragePathError
from object_storage.s3 import S3ObjectStorage


class _Body(BytesIO):
    pass


class _Paginator:
    def __init__(self, client: "_FakeS3Client") -> None:
        self.client = client

    def paginate(self, *, Bucket: str, Prefix: str):
        contents = [
            {"Key": key, "Size": len(value)}
            for (bucket, key), value in self.client.objects.items()
            if bucket == Bucket and key.startswith(Prefix)
        ]
        yield {"Contents": contents}


class _NotFound(Exception):
    def __init__(self) -> None:
        self.response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }
        super().__init__("not found")


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.presign_calls: list[tuple[str, dict, int]] = []

    def upload_fileobj(self, fileobj, bucket, key, Config=None):
        self.objects[(bucket, key)] = fileobj.read()

    def head_object(self, *, Bucket: str, Key: str):
        try:
            value = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise _NotFound() from exc
        return {"ContentLength": len(value)}

    def get_object(self, *, Bucket: str, Key: str):
        try:
            value = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise _NotFound() from exc
        return {"Body": _Body(value)}

    def delete_object(self, *, Bucket: str, Key: str):
        self.objects.pop((Bucket, Key), None)
        return {}

    def get_paginator(self, operation: str):
        assert operation == "list_objects_v2"
        return _Paginator(self)

    def generate_presigned_url(self, operation: str, *, Params: dict, ExpiresIn: int):
        self.presign_calls.append((operation, Params, ExpiresIn))
        return f"https://signed.example/{operation}/{Params['Key']}?expires={ExpiresIn}"


def test_s3_contract_streaming_listing_delete_and_tenant_isolation():
    client = _FakeS3Client()
    storage = S3ObjectStorage("objects", client=client)

    info = storage.put_fileobj("tenant-a", "docs/report.txt", BytesIO(b"abcdef"), chunk_size=2)
    storage.put_bytes("tenant-b", "docs/report.txt", b"other")

    assert info.tenant_id == "tenant-a"
    assert info.key == "docs/report.txt"
    assert info.size == 6
    assert info.uri == "s3://objects/tenants/tenant-a/docs/report.txt"
    assert storage.get_bytes("tenant-a", "docs/report.txt") == b"abcdef"
    assert list(storage.iter_bytes("tenant-a", "docs/report.txt", chunk_size=2)) == [b"ab", b"cd", b"ef"]
    assert storage.exists("tenant-a", "docs/report.txt") is True
    assert [item.key for item in storage.list_objects("tenant-a", prefix="docs")] == ["docs/report.txt"]
    assert [item.key for item in storage.list_objects("tenant-b")] == ["docs/report.txt"]

    storage.delete("tenant-a", "docs/report.txt")
    assert storage.exists("tenant-a", "docs/report.txt") is False
    assert storage.get_bytes("tenant-b", "docs/report.txt") == b"other"


def test_s3_rejects_namespace_escape_and_invalid_chunks():
    storage = S3ObjectStorage("objects", client=_FakeS3Client())

    with pytest.raises(StoragePathError):
        storage.put_bytes("tenant-a", "../tenant-b/secret.txt", b"x")
    with pytest.raises(StoragePathError):
        storage.exists("../tenant-b", "secret.txt")
    with pytest.raises(ValueError, match="chunk_size"):
        list(storage.iter_bytes("tenant-a", "safe.txt", chunk_size=0))


def test_s3_presigned_urls_remain_tenant_scoped():
    client = _FakeS3Client()
    storage = S3ObjectStorage("objects", client=client)

    download = storage.generate_presigned_download_url("tenant-a", "docs/a.pdf", expires_in=60)
    upload = storage.generate_presigned_upload_url(
        "tenant-a",
        "incoming/a.pdf",
        expires_in=120,
        content_type="application/pdf",
    )

    assert "tenants/tenant-a/docs/a.pdf" in download
    assert "tenants/tenant-a/incoming/a.pdf" in upload
    assert client.presign_calls == [
        (
            "get_object",
            {"Bucket": "objects", "Key": "tenants/tenant-a/docs/a.pdf"},
            60,
        ),
        (
            "put_object",
            {
                "Bucket": "objects",
                "Key": "tenants/tenant-a/incoming/a.pdf",
                "ContentType": "application/pdf",
            },
            120,
        ),
    ]

    with pytest.raises(ValueError, match="expires_in"):
        storage.generate_presigned_download_url("tenant-a", "docs/a.pdf", expires_in=0)
    with pytest.raises(ValueError, match="expires_in"):
        storage.generate_presigned_upload_url("tenant-a", "docs/a.pdf", expires_in=604801)


def test_s3_configuration_validation():
    with pytest.raises(ValueError, match="bare S3 bucket"):
        S3ObjectStorage("s3://bucket")
    with pytest.raises(ValueError, match="absolute http"):
        S3ObjectStorage("bucket", endpoint_url="localhost:9000")
    with pytest.raises(ValueError, match="provided together"):
        S3ObjectStorage("bucket", access_key_id="only-access")
    with pytest.raises(ValueError, match="addressing_style"):
        S3ObjectStorage("bucket", addressing_style="invalid")


def test_factory_wires_s3_environment(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("OBJECT_STORAGE_S3_BUCKET", "tenant-objects")
    monkeypatch.setenv("OBJECT_STORAGE_S3_ENDPOINT", "https://r2.example.invalid")
    monkeypatch.setenv("OBJECT_STORAGE_S3_REGION", "auto")
    monkeypatch.setenv("OBJECT_STORAGE_S3_ACCESS_KEY", "access")
    monkeypatch.setenv("OBJECT_STORAGE_S3_SECRET_KEY", "secret")
    monkeypatch.setenv("OBJECT_STORAGE_S3_ADDRESSING_STYLE", "path")
    _reset_object_storage_for_tests()
    try:
        storage = get_object_storage()
        assert isinstance(storage, S3ObjectStorage)
        assert storage.bucket_name == "tenant-objects"
        assert storage.endpoint_url == "https://r2.example.invalid"
        assert storage.region_name == "auto"
        assert storage.addressing_style == "path"
    finally:
        _reset_object_storage_for_tests()
