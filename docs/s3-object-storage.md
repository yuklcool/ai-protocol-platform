# S3-compatible ObjectStorage

The platform keeps local filesystem storage as the default self-host backend. S3-compatible storage is an explicit opt-in adapter and does **not** add MinIO, S3, Redis, or any other service to the default Docker Compose stack.

## Enable S3-compatible storage

Set the backend and bucket:

```env
OBJECT_STORAGE_BACKEND=s3
OBJECT_STORAGE_S3_BUCKET=platform-objects
OBJECT_STORAGE_S3_REGION=us-east-1
```

AWS workloads may omit explicit credentials and use the normal boto3 credential chain (for example IAM roles).

For a custom endpoint such as MinIO/AIStor, Ceph RGW, Garage, LocalStack, or another S3-compatible provider:

```env
OBJECT_STORAGE_BACKEND=s3
OBJECT_STORAGE_S3_BUCKET=platform-objects
OBJECT_STORAGE_S3_ENDPOINT=https://s3.example.internal
OBJECT_STORAGE_S3_REGION=us-east-1
OBJECT_STORAGE_S3_ACCESS_KEY=change-me
OBJECT_STORAGE_S3_SECRET_KEY=change-me
OBJECT_STORAGE_S3_ADDRESSING_STYLE=path
```

Temporary credentials can additionally set `OBJECT_STORAGE_S3_SESSION_TOKEN`.

Cloudflare R2 commonly uses its account endpoint with `OBJECT_STORAGE_S3_REGION=auto`. Addressing style can be `auto`, `path`, or `virtual`.

## Tenant isolation

Business code continues to address objects as `(tenant_id, key)`. The adapter maps those values to:

```text
tenants/<tenant_id>/<key>
```

Tenant IDs and object keys use the same path-safety validation as local and GCS storage. Callers cannot use `..`, absolute paths, backslashes, empty path segments, or tenant IDs containing path separators to escape a tenant namespace.

## Streaming transfers

`put_fileobj()` uses boto3's managed multipart upload and keeps transfer memory bounded. The requested `chunk_size` is promoted to S3's 5 MiB multipart minimum when needed. `iter_bytes()` reads `StreamingBody` chunks incrementally and closes the response body when iteration completes or is aborted.

The existing convenience methods remain available:

- `put_bytes()`
- `get_bytes()`
- `exists()`
- `delete()`
- `list_objects()`

## Presigned direct transfer URLs

Remote object stores implement the provider-neutral presigned URL methods:

```python
storage.generate_presigned_download_url(
    tenant_id,
    "documents/report.pdf",
    expires_in=900,
)

storage.generate_presigned_upload_url(
    tenant_id,
    "incoming/report.pdf",
    expires_in=900,
    content_type="application/pdf",
)
```

The object key is tenant-prefixed **before** signing, so a URL for one tenant does not sign an object in another tenant namespace. Expiration must be between 1 second and 7 days.

If `content_type` is supplied for an upload URL, the uploader must send the same `Content-Type` value because it becomes part of the signed request.

`LocalObjectStorage` intentionally does not generate presigned URLs. Local files continue to use authenticated application upload/download endpoints and never expose filesystem paths as transferable URLs.

## Default Compose behavior

No S3-compatible service is started by `docker-compose.yml` or `docker-compose.release.yml`. The baseline remains:

```env
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_ROOT=/data/objects
```

Switching to S3 only changes the object-storage adapter selected by the backend; business document code continues to use the same `ObjectStorage` contract.
