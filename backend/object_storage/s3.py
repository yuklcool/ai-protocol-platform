"""S3-compatible adapter for the provider-neutral ObjectStorage API.

The adapter works with AWS S3 and S3-compatible endpoints such as Cloudflare
R2, MinIO/AIStor, Ceph RGW, Garage and LocalStack. Objects always live beneath
``tenants/<tenant_id>/`` so switching providers does not weaken the platform's
tenant namespace boundary.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, BinaryIO
from urllib.parse import urlparse

from object_storage.base import ObjectInfo
from object_storage.local import _validate_key, _validate_tenant_id

_MIN_MULTIPART_CHUNK = 5 * 1024 * 1024
_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}
_MAX_PRESIGN_SECONDS = 7 * 24 * 60 * 60


def _is_not_found(exc: Exception) -> bool:
    """Return True for botocore-compatible not-found errors without importing it."""

    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error")
    code = str(error.get("Code", "")) if isinstance(error, dict) else ""
    metadata = response.get("ResponseMetadata")
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return code in _NOT_FOUND_CODES or status == 404


def _validate_presign_expiry(expires_in: int) -> int:
    value = int(expires_in)
    if value <= 0 or value > _MAX_PRESIGN_SECONDS:
        raise ValueError("expires_in must be between 1 and 604800 seconds")
    return value


class S3ObjectStorage:
    """Store tenant objects in an S3-compatible bucket.

    Explicit credentials are optional. When access/secret keys are omitted,
    boto3's normal credential provider chain is used (for example IAM roles in
    AWS). Self-hosted S3-compatible deployments normally provide explicit
    credentials plus ``endpoint_url`` and ``addressing_style='path'``.
    """

    def __init__(
        self,
        bucket_name: str,
        *,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        session_token: str | None = None,
        addressing_style: str = "auto",
        client: Any | None = None,
    ) -> None:
        bucket = bucket_name.strip()
        if not bucket or "/" in bucket or bucket.startswith("s3://"):
            raise ValueError("bucket_name must be a bare S3 bucket name")

        endpoint = endpoint_url.strip() if endpoint_url else ""
        if endpoint:
            parsed = urlparse(endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("endpoint_url must be an absolute http(s) URL")

        access_key = access_key_id.strip() if access_key_id else ""
        secret_key = secret_access_key.strip() if secret_access_key else ""
        if bool(access_key) != bool(secret_key):
            raise ValueError("access_key_id and secret_access_key must be provided together")
        token = session_token.strip() if session_token else ""
        if token and not access_key:
            raise ValueError("session_token requires explicit access_key_id and secret_access_key")

        style = addressing_style.strip().lower() or "auto"
        if style not in {"auto", "path", "virtual"}:
            raise ValueError("addressing_style must be one of: auto, path, virtual")

        self.bucket_name = bucket
        self.endpoint_url = endpoint or None
        self.region_name = (region_name or "us-east-1").strip() or "us-east-1"
        self.access_key_id = access_key or None
        self.secret_access_key = secret_key or None
        self.session_token = token or None
        self.addressing_style = style
        self._client = client

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc:  # pragma: no cover - exercised by deployment packaging
                raise RuntimeError(
                    "S3 object storage requires the boto3 optional dependency; "
                    "install the backend with the S3 dependency enabled"
                ) from exc

            kwargs: dict[str, Any] = {
                "region_name": self.region_name,
                "config": Config(
                    s3={"addressing_style": self.addressing_style},
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            }
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            if self.access_key_id:
                kwargs["aws_access_key_id"] = self.access_key_id
                kwargs["aws_secret_access_key"] = self.secret_access_key
            if self.session_token:
                kwargs["aws_session_token"] = self.session_token
            self._client = boto3.client("s3", **kwargs)
        return self._client

    def _object_name(self, tenant_id: str, key: str) -> tuple[str, str]:
        tenant = _validate_tenant_id(tenant_id)
        normalized = _validate_key(key).as_posix()
        return f"tenants/{tenant}/{normalized}", normalized

    def _info(self, tenant_id: str, normalized: str, object_name: str, size: int) -> ObjectInfo:
        return ObjectInfo(
            tenant_id=tenant_id,
            key=normalized,
            size=int(size),
            uri=f"s3://{self.bucket_name}/{object_name}",
        )

    def put_bytes(self, tenant_id: str, key: str, data: bytes) -> ObjectInfo:
        from io import BytesIO

        return self.put_fileobj(tenant_id, key, BytesIO(data))

    def put_fileobj(
        self,
        tenant_id: str,
        key: str,
        fileobj: BinaryIO,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> ObjectInfo:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        try:
            from boto3.s3.transfer import TransferConfig
        except ImportError as exc:  # pragma: no cover - exercised by deployment packaging
            raise RuntimeError(
                "S3 object storage requires the boto3 optional dependency; "
                "install the backend with the S3 dependency enabled"
            ) from exc

        object_name, normalized = self._object_name(tenant_id, key)
        transfer_chunk = max(chunk_size, _MIN_MULTIPART_CHUNK)
        config = TransferConfig(
            multipart_threshold=transfer_chunk,
            multipart_chunksize=transfer_chunk,
            max_concurrency=1,
            use_threads=False,
        )
        client = self._get_client()
        client.upload_fileobj(fileobj, self.bucket_name, object_name, Config=config)
        head = client.head_object(Bucket=self.bucket_name, Key=object_name)
        return self._info(tenant_id, normalized, object_name, int(head.get("ContentLength", 0) or 0))

    def get_bytes(self, tenant_id: str, key: str) -> bytes:
        object_name, _ = self._object_name(tenant_id, key)
        body = self._get_client().get_object(Bucket=self.bucket_name, Key=object_name)["Body"]
        try:
            return body.read()
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    def iter_bytes(self, tenant_id: str, key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        object_name, _ = self._object_name(tenant_id, key)
        body = self._get_client().get_object(Bucket=self.bucket_name, Key=object_name)["Body"]
        try:
            while True:
                chunk = body.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    def exists(self, tenant_id: str, key: str) -> bool:
        object_name, _ = self._object_name(tenant_id, key)
        try:
            self._get_client().head_object(Bucket=self.bucket_name, Key=object_name)
            return True
        except Exception as exc:
            if _is_not_found(exc):
                return False
            raise

    def delete(self, tenant_id: str, key: str) -> None:
        object_name, _ = self._object_name(tenant_id, key)
        # S3 DELETE is idempotent for a missing key, so no pre-flight HEAD is
        # needed (and avoiding it also removes a race between HEAD and DELETE).
        self._get_client().delete_object(Bucket=self.bucket_name, Key=object_name)

    def list_objects(self, tenant_id: str, *, prefix: str = "") -> list[ObjectInfo]:
        tenant = _validate_tenant_id(tenant_id)
        normalized_prefix = _validate_key(prefix).as_posix() if prefix else ""
        namespace = f"tenants/{tenant}/"
        paginator = self._get_client().get_paginator("list_objects_v2")
        result: list[ObjectInfo] = []
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=namespace + normalized_prefix):
            for item in page.get("Contents", []):
                name = str(item.get("Key", ""))
                if not name.startswith(namespace):
                    continue
                key = name[len(namespace) :]
                if not key:
                    continue
                result.append(
                    self._info(
                        tenant_id,
                        key,
                        name,
                        int(item.get("Size", 0) or 0),
                    )
                )
        result.sort(key=lambda item: item.key)
        return result

    def generate_presigned_download_url(
        self,
        tenant_id: str,
        key: str,
        *,
        expires_in: int = 900,
    ) -> str:
        """Return a time-limited GET URL scoped to one tenant object."""

        object_name, _ = self._object_name(tenant_id, key)
        return str(
            self._get_client().generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_name},
                ExpiresIn=_validate_presign_expiry(expires_in),
            )
        )

    def generate_presigned_upload_url(
        self,
        tenant_id: str,
        key: str,
        *,
        expires_in: int = 900,
        content_type: str | None = None,
    ) -> str:
        """Return a time-limited PUT URL scoped to one tenant object."""

        object_name, _ = self._object_name(tenant_id, key)
        params: dict[str, str] = {"Bucket": self.bucket_name, "Key": object_name}
        if content_type:
            params["ContentType"] = content_type
        return str(
            self._get_client().generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=_validate_presign_expiry(expires_in),
            )
        )
