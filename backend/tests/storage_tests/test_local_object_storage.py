from __future__ import annotations

from pathlib import Path

import pytest

from object_storage.local import LocalObjectStorage, StoragePathError


def test_round_trip_survives_adapter_reconstruction(tmp_path: Path):
    root = tmp_path / "objects"
    first = LocalObjectStorage(root)
    info = first.put_bytes("tenant-a", "docs/folder/report.txt", b"persistent-data")

    assert info.tenant_id == "tenant-a"
    assert info.key == "docs/folder/report.txt"
    assert info.size == len(b"persistent-data")
    assert info.uri.startswith("file://")

    # Reconstruct the adapter to model a backend process restart. No in-process
    # cache is allowed to be necessary for recovery.
    second = LocalObjectStorage(root)
    assert second.get_bytes("tenant-a", "docs/folder/report.txt") == b"persistent-data"
    assert second.exists("tenant-a", "docs/folder/report.txt")


def test_tenants_are_hard_namespaces(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "objects")
    storage.put_bytes("tenant-a", "same/name.txt", b"A")
    storage.put_bytes("tenant-b", "same/name.txt", b"B")

    assert storage.get_bytes("tenant-a", "same/name.txt") == b"A"
    assert storage.get_bytes("tenant-b", "same/name.txt") == b"B"
    assert [o.key for o in storage.list_objects("tenant-a")] == ["same/name.txt"]
    assert [o.key for o in storage.list_objects("tenant-b")] == ["same/name.txt"]


@pytest.mark.parametrize(
    "key",
    [
        "../secret.txt",
        "docs/../../secret.txt",
        "/etc/passwd",
        r"..\\secret.txt",
        "docs/./file.txt",
        "docs/../file.txt",
        "bad\x00name.txt",
        "",
    ],
)
def test_rejects_unsafe_object_keys(tmp_path: Path, key: str):
    storage = LocalObjectStorage(tmp_path / "objects")
    with pytest.raises(StoragePathError):
        storage.put_bytes("tenant-a", key, b"x")


@pytest.mark.parametrize("tenant_id", ["", ".", "..", "../other", "a/b", r"a\\b", "bad\x00id"])
def test_rejects_unsafe_tenant_ids(tmp_path: Path, tenant_id: str):
    storage = LocalObjectStorage(tmp_path / "objects")
    with pytest.raises(StoragePathError):
        storage.put_bytes(tenant_id, "safe.txt", b"x")


def test_symlink_escape_is_rejected(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "objects")
    tenant_root = storage.root_dir / "tenants" / "tenant-a"
    tenant_root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tenant_root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(StoragePathError):
        storage.put_bytes("tenant-a", "link/secret.txt", b"must-not-escape")
    assert not (outside / "secret.txt").exists()


def test_streaming_read_is_chunked(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "objects")
    storage.put_bytes("tenant-a", "large.bin", b"abcdefghij")

    chunks = list(storage.iter_bytes("tenant-a", "large.bin", chunk_size=3))
    assert chunks == [b"abc", b"def", b"ghi", b"j"]
    assert b"".join(chunks) == b"abcdefghij"


def test_delete_is_idempotent_and_does_not_touch_other_tenant(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "objects")
    storage.put_bytes("tenant-a", "docs/a.txt", b"A")
    storage.put_bytes("tenant-b", "docs/a.txt", b"B")

    storage.delete("tenant-a", "docs/a.txt")
    storage.delete("tenant-a", "docs/a.txt")

    assert not storage.exists("tenant-a", "docs/a.txt")
    assert storage.get_bytes("tenant-b", "docs/a.txt") == b"B"
