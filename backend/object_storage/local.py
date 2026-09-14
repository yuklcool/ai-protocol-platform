"""Tenant-isolated local filesystem object storage.

Self-hosted deployments mount a persistent Docker volume at ``/data`` and use
this adapter by default.  Files live under::

    <root>/tenants/<tenant_id>/<key>

The adapter never exposes the root directory directly to callers and rejects
absolute paths, traversal, backslash path tricks, NUL bytes, and symlink escapes.
Writes are atomic (temporary file + ``os.replace``), and reads can be streamed in
bounded chunks so large downloads do not need to be buffered in memory.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from object_storage.base import ObjectInfo


class StoragePathError(ValueError):
    """Raised when a tenant id or object key would escape its storage scope."""


def _validate_tenant_id(tenant_id: str) -> str:
    value = tenant_id.strip()
    if not value:
        raise StoragePathError("tenant_id must not be empty")
    if "\x00" in value or "/" in value or "\\" in value or value in {".", ".."}:
        raise StoragePathError("tenant_id contains an unsafe path segment")
    return value


def _validate_key(key: str, *, allow_empty: bool = False) -> PurePosixPath:
    value = key.strip()
    if not value:
        if allow_empty:
            return PurePosixPath(".")
        raise StoragePathError("object key must not be empty")
    if "\x00" in value or "\\" in value:
        raise StoragePathError("object key contains an unsafe path sequence")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise StoragePathError("object key must be a normalized relative POSIX path")
    return path


class LocalObjectStorage:
    """Filesystem implementation of the platform ``ObjectStorage`` contract."""

    def __init__(self, root_dir: str | Path = "/data/objects") -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _tenant_root(self, tenant_id: str) -> Path:
        safe_tenant = _validate_tenant_id(tenant_id)
        root = (self.root_dir / "tenants" / safe_tenant).resolve(strict=False)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _resolve(self, tenant_id: str, key: str) -> tuple[Path, str]:
        tenant_root = self._tenant_root(tenant_id)
        normalized = _validate_key(key).as_posix()
        candidate = (tenant_root / normalized).resolve(strict=False)
        try:
            candidate.relative_to(tenant_root.resolve())
        except ValueError as exc:
            raise StoragePathError("object key escapes tenant storage namespace") from exc
        return candidate, normalized

    def _info(self, tenant_id: str, key: str, path: Path) -> ObjectInfo:
        return ObjectInfo(
            tenant_id=tenant_id,
            key=key,
            size=path.stat().st_size,
            uri=path.resolve().as_uri(),
        )

    def put_bytes(self, tenant_id: str, key: str, data: bytes) -> ObjectInfo:
        path, normalized = self._resolve(tenant_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Keep the temporary file in the destination directory so os.replace is
        # atomic even when /data is a separately-mounted filesystem.
        temp = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
        try:
            with temp.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)
        return self._info(tenant_id, normalized, path)

    def get_bytes(self, tenant_id: str, key: str) -> bytes:
        path, _ = self._resolve(tenant_id, key)
        return path.read_bytes()

    def iter_bytes(
        self,
        tenant_id: str,
        key: str,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        path, _ = self._resolve(tenant_id, key)
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def exists(self, tenant_id: str, key: str) -> bool:
        path, _ = self._resolve(tenant_id, key)
        return path.is_file()

    def delete(self, tenant_id: str, key: str) -> None:
        path, _ = self._resolve(tenant_id, key)
        if not path.exists():
            return
        if not path.is_file():
            raise StoragePathError("object key does not resolve to a regular file")
        path.unlink()

        # Best-effort pruning, stopping at the tenant root.  This keeps repeated
        # upload/delete cycles from leaving a deep tree of empty directories.
        tenant_root = self._tenant_root(tenant_id).resolve()
        parent = path.parent
        while parent != tenant_root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def list_objects(self, tenant_id: str, *, prefix: str = "") -> list[ObjectInfo]:
        tenant_root = self._tenant_root(tenant_id)
        if prefix:
            prefix_path = _validate_key(prefix)
            scan_root = (tenant_root / prefix_path).resolve(strict=False)
            try:
                scan_root.relative_to(tenant_root.resolve())
            except ValueError as exc:
                raise StoragePathError("prefix escapes tenant storage namespace") from exc
        else:
            scan_root = tenant_root

        if not scan_root.exists():
            return []
        if scan_root.is_file():
            rel = scan_root.relative_to(tenant_root).as_posix()
            return [self._info(tenant_id, rel, scan_root)]

        result: list[ObjectInfo] = []
        for path in sorted(scan_root.rglob("*")):
            if not path.is_file() or path.name.startswith(".") and ".tmp-" in path.name:
                continue
            resolved = path.resolve()
            try:
                rel = resolved.relative_to(tenant_root.resolve()).as_posix()
            except ValueError as exc:
                # A symlink placed into the volume by an operator must not turn
                # listing into a cross-namespace read primitive.
                raise StoragePathError("storage tree contains a path outside the tenant namespace") from exc
            result.append(self._info(tenant_id, rel, resolved))
        return result
