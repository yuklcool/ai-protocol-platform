from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest

from object_storage.gcs import GcsObjectStorage, LegacyGcsObjectStorage


class FakeBlob:
    def __init__(self, bucket, name: str):
        self.bucket = bucket
        self.name = name
        self.chunk_size = None
        self.size = len(bucket.data.get(name, b""))

    def upload_from_file(self, fileobj, rewind=False):
        if rewind:
            fileobj.seek(0)
        self.bucket.data[self.name] = fileobj.read()
        self.size = len(self.bucket.data[self.name])

    def reload(self):
        self.size = len(self.bucket.data.get(self.name, b""))

    def download_as_bytes(self):
        return self.bucket.data[self.name]

    def open(self, mode: str):
        assert mode == "rb"
        return BytesIO(self.bucket.data[self.name])

    def exists(self):
        return self.name in self.bucket.data

    def delete(self):
        self.bucket.data.pop(self.name, None)


class FakeBucket:
    def __init__(self):
        self.data: dict[str, bytes] = {}

    def blob(self, name: str):
        return FakeBlob(self, name)


class FakeClient:
    def __init__(self):
        self.buckets: dict[str, FakeBucket] = {}

    def bucket(self, name: str):
        return self.buckets.setdefault(name, FakeBucket())

    def list_blobs(self, bucket_name: str, prefix: str = ""):
        bucket = self.bucket(bucket_name)
        return [SimpleNamespace(name=name, size=len(data)) for name, data in bucket.data.items() if name.startswith(prefix)]


def test_gcs_fileobj_upload_uses_tenant_prefix() -> None:
    client = FakeClient()
    storage = GcsObjectStorage("docs", client=client)

    info = storage.put_fileobj("example.com", "users/u/docs/a.pdf", BytesIO(b"pdf-data"))

    assert info.uri == "gs://docs/tenants/example.com/users/u/docs/a.pdf"
    assert client.bucket("docs").data["tenants/example.com/users/u/docs/a.pdf"] == b"pdf-data"
    assert storage.get_bytes("example.com", "users/u/docs/a.pdf") == b"pdf-data"
    assert [item.key for item in storage.list_objects("example.com")] == ["users/u/docs/a.pdf"]


def test_gcs_tenants_do_not_share_same_key() -> None:
    client = FakeClient()
    storage = GcsObjectStorage("docs", client=client)
    storage.put_bytes("tenant-a", "same.txt", b"A")
    storage.put_bytes("tenant-b", "same.txt", b"B")

    assert storage.get_bytes("tenant-a", "same.txt") == b"A"
    assert storage.get_bytes("tenant-b", "same.txt") == b"B"


def test_legacy_adapter_reads_old_layout_but_refuses_writes() -> None:
    client = FakeClient()
    bucket = client.bucket("legacy")
    bucket.data["users/u/docs/old.pdf"] = b"old"
    storage = LegacyGcsObjectStorage("legacy", client=client)

    assert storage.get_bytes("example.com", "users/u/docs/old.pdf") == b"old"
    with pytest.raises(RuntimeError):
        storage.put_fileobj("example.com", "users/u/docs/new.pdf", BytesIO(b"new"))
