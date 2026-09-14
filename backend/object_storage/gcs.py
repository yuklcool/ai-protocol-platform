"""Google Cloud Storage adapter for the provider-neutral ObjectStorage API."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from object_storage.base import ObjectInfo
from object_storage.local import _validate_key, _validate_tenant_id


class GcsObjectStorage:
    """Store tenant objects beneath ``tenants/<tenant_id>/`` in one GCS bucket.

    The client is lazy so importing the platform or selecting another backend
    never attempts ADC discovery.  Authorization metadata remains in PostgreSQL;
    this adapter is responsible only for namespaced bytes.
    """

    def __init__(self, bucket_name: str, *, client: Any | None = None) -> None:
        bucket = bucket_name.strip()
        if not bucket or "/" in bucket or bucket.startswith("gs://"):
            raise ValueError("bucket_name must be a bare GCS bucket name")
        self.bucket_name = bucket
        self._client = client

    def _get_client(self):
        if self._client is None:
            from google.cloud import storage as gcs

            self._client = gcs.Client()
        return self._client

    def _object_name(self, tenant_id: str, key: str) -> tuple[str, str]:
        tenant = _validate_tenant_id(tenant_id)
        normalized = _validate_key(key).as_posix()
        return f"tenants/{tenant}/{normalized}", normalized

    def _blob(self, tenant_id: str, key: str):
        object_name, normalized = self._object_name(tenant_id, key)
        blob = self._get_client().bucket(self.bucket_name).blob(object_name)
        return blob, normalized

    def put_bytes(self, tenant_id: str, key: str, data: bytes) -> ObjectInfo:
        blob, normalized = self._blob(tenant_id, key)
        blob.upload_from_string(data)
        return ObjectInfo(
            tenant_id=tenant_id,
            key=normalized,
            size=len(data),
            uri=f"gs://{self.bucket_name}/{blob.name}",
        )

    def get_bytes(self, tenant_id: str, key: str) -> bytes:
        blob, _ = self._blob(tenant_id, key)
        return blob.download_as_bytes()

    def iter_bytes(
        self,
        tenant_id: str,
        key: str,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        blob, _ = self._blob(tenant_id, key)
        # Blob.open performs range/chunked reads rather than materialising the
        # whole object, keeping the same bounded-memory contract as local files.
        with blob.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def exists(self, tenant_id: str, key: str) -> bool:
        blob, _ = self._blob(tenant_id, key)
        return bool(blob.exists())

    def delete(self, tenant_id: str, key: str) -> None:
        blob, _ = self._blob(tenant_id, key)
        try:
            blob.delete()
        except Exception as exc:
            # google-cloud-storage raises NotFound for an absent object. Avoid a
            # hard dependency on the exception type here so fake clients remain
            # lightweight; only swallow explicit 404-ish provider errors.
            if getattr(exc, "code", None) == 404 or getattr(exc, "status_code", None) == 404:
                return
            raise

    def list_objects(self, tenant_id: str, *, prefix: str = "") -> list[ObjectInfo]:
        tenant = _validate_tenant_id(tenant_id)
        normalized_prefix = _validate_key(prefix).as_posix() if prefix else ""
        namespace = f"tenants/{tenant}/"
        provider_prefix = namespace + normalized_prefix
        blobs = self._get_client().list_blobs(self.bucket_name, prefix=provider_prefix)

        result: list[ObjectInfo] = []
        for blob in blobs:
            name = str(blob.name)
            if not name.startswith(namespace):
                continue
            key = name[len(namespace) :]
            if not key:
                continue
            result.append(
                ObjectInfo(
                    tenant_id=tenant_id,
                    key=key,
                    size=int(blob.size or 0),
                    uri=f"gs://{self.bucket_name}/{name}",
                )
            )
        result.sort(key=lambda item: item.key)
        return result
