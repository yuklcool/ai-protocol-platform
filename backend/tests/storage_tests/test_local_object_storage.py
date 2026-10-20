from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from object_storage.local import LocalObjectStorage, StoragePathError


def test_round_trip_survives_adapter_reconstruction(tmp_path: Path):
    root = tmp_path / "objects"
    first = LocalObjectStorage(root)
    info = first.put_bytes("user-a", "docs/folder/report.txt", b"persistent-data")

    assert info.user_id == "user-a"
    assert info.key == "docs/folder/report.txt"
    assert info.size == len(b"persistent-data")
    assert info.uri.startswith("file://")

    second = LocalObjectStorage(root)
    assert second.get_bytes("user-a", "docs/folder/report.txt") == b"persistent-data"
    assert second.exists("user-a", "docs/folder/report.txt")


def test_file_object_upload_is_chunked_and_atomic(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "objects")
    payload = b"0123456789" * 1000
    info = storage.put_fileobj("user-a", "streamed.bin", BytesIO(payload), chunk_size=97)

    assert info.size == len(payload)
    assert storage.get_bytes("user-a", "streamed.bin") == payload
    user_dir = storage.root_dir / "users" / "user-a"
    assert not list(user_dir.glob(".*.tmp-*"))


def test_users_are_hard_namespaces(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "objects")
    storage.put_bytes("user-a", "same/name.txt", b"A")
    storage.put_bytes("user-b", "same/name.txt", b"B")

    assert storage.get_bytes("user-a", "same/name.txt") == b"A"
    assert storage.get_bytes("user-b", "same/name.txt") == b"B"
    assert [o.key for o in storage.list_objects("user-a")] == ["same/name.txt"]
    assert [o.key for o in storage.list_objects("user-b")] == ["same/name.txt"]


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
        storage.put_bytes("user-a", key, b"x")


@pytest.mark.parametrize("user_id", ["", ".", "..", "../other", "a/b", r"a\\b", "bad\x00id"])
def test_rejects_unsafe_user_ids(tmp_path: Path, user_id: str):
    storage = LocalObjectStorage(tmp_path / "objects")
    with pytest.raises(StoragePathError):
        storage.put_bytes(user_id, "safe.txt", b"x")


def test_symlink_escape_is_rejected(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "objects")
    user_root = storage.root_dir / "users" / "user-a"
    user_root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (user_root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(StoragePathError):
        storage.put_bytes("user-a", "link/secret.txt", b"must-not-escape")
    assert not (outside / "secret.txt").exists()


def test_streaming_read_is_chunked(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "objects")
    storage.put_bytes("user-a", "large.bin", b"abcdefghij")

    chunks = list(storage.iter_bytes("user-a", "large.bin", chunk_size=3))
    assert chunks == [b"abc", b"def", b"ghi", b"j"]
    assert b"".join(chunks) == b"abcdefghij"


def test_delete_is_idempotent_and_does_not_touch_other_user(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "objects")
    storage.put_bytes("user-a", "docs/a.txt", b"A")
    storage.put_bytes("user-b", "docs/a.txt", b"B")

    storage.delete("user-a", "docs/a.txt")
    storage.delete("user-a", "docs/a.txt")

    assert not storage.exists("user-a", "docs/a.txt")
    assert storage.get_bytes("user-b", "docs/a.txt") == b"B"
