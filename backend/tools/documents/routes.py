"""FastAPI routes for user folders and provider-neutral document access."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db.folders as folders_db
from auth import User, get_current_user
from db.clients import resolve_documents_bucket
from db.persistence import delete_document as _delete_document_record
from db.persistence import get_document as _get_document_record
from db.persistence import set_document as _set_document_record
from object_storage import get_object_storage, object_storage_backend_name
from object_storage.gcs import GcsObjectStorage, LegacyGcsObjectStorage
from object_storage.local import LocalObjectStorage

log = logging.getLogger(__name__)
router = APIRouter(tags=["doc-folders"])
_CurrentUser = Annotated[User, Depends(get_current_user)]
_ACCESS_DENIED = "Access denied"
_PARSED_DOCS_COLLECTION = "parsed_documents"


def _content_disposition(disposition: str, filename: str) -> str:
    from urllib.parse import quote

    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").strip()
    ascii_fallback = ascii_fallback.replace("\\", "_").replace('"', "_") or "document"
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def _tenant_namespace(user: User) -> str:
    """Resolve the stable tenant attached to the authenticated identity.

    ``tenant_id`` is authoritative. Domain remains only as the compatibility
    mapping for identities that predate first-class tenant claims. We do not
    parse arbitrary email text and never invent a pseudo tenant from the uid.
    """
    tenant_id = (getattr(user, "tenant_id", None) or getattr(user, "domain", None) or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Stable tenant scope is required")
    return tenant_id


def _owned_document(doc_id: str, user: User) -> dict:
    doc = _get_document_record(_PARSED_DOCS_COLLECTION, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.get("userId") != user.uid:
        raise HTTPException(status_code=403, detail=_ACCESS_DENIED)

    viewer_tenant = _tenant_namespace(user)
    resource_tenant = str(doc.get("tenantId") or "").strip()
    # ParsedDocument is now a first-class tenant resource. Legacy rows without
    # tenantId must be explicitly migrated/hydrated; request-time reads do not
    # guess a tenant from email/domain because that would re-open cross-tenant
    # access for the same uid.
    if not resource_tenant or resource_tenant != viewer_tenant:
        raise HTTPException(status_code=403, detail=_ACCESS_DENIED)

    doc.setdefault("id", doc_id)
    return doc


def _storage_binding(doc: dict, user: User):
    """Return (storage, tenant_id, key, backend) for an authorized document."""
    tenant_id = str(doc.get("tenantId") or "").strip()
    if not tenant_id or tenant_id != _tenant_namespace(user):
        raise HTTPException(status_code=403, detail=_ACCESS_DENIED)

    key = (doc.get("storagePath") or "").strip()
    source_url = (doc.get("sourceUrl") or "").strip()
    backend = (doc.get("storageBackend") or "").strip().lower()

    if not key and source_url.startswith("gs://"):
        parsed = urlparse(source_url)
        key = parsed.path.lstrip("/")
    if not key:
        raise HTTPException(status_code=404, detail="Document has no stored binary")

    if backend == "local":
        root = os.environ.get("OBJECT_STORAGE_LOCAL_ROOT", "/data/objects").strip() or "/data/objects"
        return LocalObjectStorage(root), tenant_id, key, backend

    if backend == "gcs":
        parsed = urlparse(source_url) if source_url.startswith("gs://") else None
        bucket = parsed.netloc if parsed and parsed.netloc else resolve_documents_bucket(user)
        return GcsObjectStorage(bucket), tenant_id, key, backend

    if backend == "gcs-legacy":
        parsed = urlparse(source_url) if source_url.startswith("gs://") else None
        bucket = parsed.netloc if parsed and parsed.netloc else resolve_documents_bucket(user)
        return LegacyGcsObjectStorage(bucket), tenant_id, key, backend

    if backend == "s3":
        if object_storage_backend_name() != "s3":
            raise HTTPException(status_code=503, detail="Document storage backend s3 is not configured")
        return get_object_storage(), tenant_id, key, backend

    if source_url.startswith("gs://"):
        parsed = urlparse(source_url)
        if not parsed.netloc:
            raise HTTPException(status_code=500, detail="Malformed sourceUrl on document")
        return LegacyGcsObjectStorage(parsed.netloc), tenant_id, key, "gcs-legacy"

    if object_storage_backend_name() == "local":
        return get_object_storage(), tenant_id, key, "local"

    raise HTTPException(status_code=503, detail="Document storage backend is unknown")


def _content_type_for(doc: dict) -> str:
    if doc.get("contentType"):
        return str(doc["contentType"])
    source_format = (doc.get("sourceFormat") or "").lower().lstrip(".")
    return {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "html": "text/html",
        "htm": "text/html",
        "md": "text/markdown",
        "csv": "text/csv",
        "txt": "text/plain",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }.get(source_format, "application/octet-stream")


def _stream_document(doc: dict, user: User, *, disposition: str):
    from fastapi.responses import StreamingResponse

    storage, tenant_id, key, _ = _storage_binding(doc, user)
    try:
        if not storage.exists(tenant_id, key):
            raise HTTPException(status_code=404, detail="Stored document binary not found")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("document exists check failed tenant=%s key=%s: %s", tenant_id, key, exc)
        raise HTTPException(status_code=502, detail="Could not access document storage") from exc

    filename = doc.get("originalFilename") or "document"
    return StreamingResponse(
        storage.iter_bytes(tenant_id, key),
        media_type=_content_type_for(doc),
        headers={
            "Content-Disposition": _content_disposition(disposition, filename),
            "Cache-Control": "private, max-age=300" if disposition == "inline" else "private, no-store",
        },
    )


class _CreateFolderRequest(BaseModel):
    name: str


class _FolderResponse(BaseModel):
    id: str
    name: str
    userId: str
    docCount: int = 0
    parsedCount: int = 0


class _FoldersListResponse(BaseModel):
    folders: list[_FolderResponse]


class _DocumentsListResponse(BaseModel):
    documents: list[dict]


@router.post("/api/folders", status_code=201)
def create_folder(body: _CreateFolderRequest, user: _CurrentUser) -> _FolderResponse:
    tenant_id = _tenant_namespace(user)
    return _FolderResponse(**folders_db.create_folder(user_id=user.uid, name=body.name, tenant_id=tenant_id))


@router.get("/api/folders")
def list_folders(user: _CurrentUser) -> _FoldersListResponse:
    tenant_id = _tenant_namespace(user)
    items = folders_db.list_folders(user_id=user.uid, tenant_id=tenant_id)
    return _FoldersListResponse(folders=[_FolderResponse(**f) for f in items])


@router.get("/api/folders/{folder_id}/documents")
def list_folder_documents(folder_id: str, user: _CurrentUser) -> _DocumentsListResponse:
    tenant_id = _tenant_namespace(user)
    folder = folders_db.get_folder(user_id=user.uid, folder_id=folder_id, tenant_id=tenant_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder.get("userId") != user.uid:
        raise HTTPException(status_code=403, detail=_ACCESS_DENIED)
    return _DocumentsListResponse(
        documents=folders_db.list_folder_documents(user_id=user.uid, folder_id=folder_id, tenant_id=tenant_id)
    )


@router.get("/api/documents/{doc_id}")
def get_document(doc_id: str, user: _CurrentUser) -> dict:
    return _owned_document(doc_id, user)


@router.get("/api/documents/{doc_id}/preview")
def preview_document(doc_id: str, user: _CurrentUser):
    return _stream_document(_owned_document(doc_id, user), user, disposition="inline")


@router.get("/api/documents/{doc_id}/download")
def download_document(doc_id: str, user: _CurrentUser):
    return _stream_document(_owned_document(doc_id, user), user, disposition="attachment")


@router.get("/api/documents/{doc_id}/thumbnail")
def thumbnail_document(doc_id: str, user: _CurrentUser, width: int = 600):
    from fastapi.responses import Response
    from tools.documents.thumbnail import cache_get, cache_put, is_thumbnailable, render_thumbnail_png

    width = max(64, min(1600, int(width)))
    doc = _owned_document(doc_id, user)
    source_format = doc.get("sourceFormat") or doc.get("originalFilename") or ""
    if not is_thumbnailable(source_format):
        raise HTTPException(status_code=415, detail="Thumbnails are only rendered for PDFs and images")

    cache_key = f"doc:{doc_id}:{doc.get('updatedAt', '')}:{width}"
    cached = cache_get(cache_key)
    if cached is not None:
        return Response(content=cached, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})

    storage, tenant_id, key, _ = _storage_binding(doc, user)
    try:
        data = storage.get_bytes(tenant_id, key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Stored document binary not found") from exc
    except Exception as exc:
        log.error("thumbnail storage read failed tenant=%s key=%s: %s", tenant_id, key, exc)
        raise HTTPException(status_code=502, detail="Could not fetch document bytes") from exc

    try:
        png = render_thumbnail_png(data, source_format, target_width=width)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Could not render thumbnail: {exc}") from exc

    cache_put(cache_key, png)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/api/documents/{doc_id}/reparse")
async def reparse_document(doc_id: str, user: _CurrentUser) -> dict:
    from tools.documents.upload import _run_parse

    doc = _owned_document(doc_id, user)
    storage, tenant_id, key, backend = _storage_binding(doc, user)
    try:
        data = storage.get_bytes(tenant_id, key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Stored document binary not found") from exc
    except Exception as exc:
        log.error("reparse storage read failed tenant=%s key=%s: %s", tenant_id, key, exc)
        raise HTTPException(status_code=502, detail="Could not fetch document bytes") from exc

    filename = doc.get("originalFilename") or key.rsplit("/", 1)[-1]
    source_ref = doc.get("sourceUrl") or f"{backend}:{tenant_id}/{key}"
    status, blocks, elapsed_ms, error = await _run_parse(data, filename, source_ref=source_ref)
    now = datetime.now(UTC)
    update = {
        "parseStatus": status,
        "status": status,
        "blocks": blocks if status == "parsed" else [],
        "blockCount": len(blocks) if status == "parsed" else None,
        "tableCount": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "table") if blocks else None,
        "imageCount": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "image") if blocks else None,
        "changeCount": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "change") if blocks else None,
        "parsedMs": elapsed_ms if status == "parsed" else None,
        "parseError": error if status == "failed" else None,
        "parsedAt": now.isoformat() if status == "parsed" else None,
        "updatedAt": now.isoformat(),
    }
    _set_document_record(_PARSED_DOCS_COLLECTION, doc_id, update, merge=True)
    return {"docId": doc_id, "parseStatus": status, "blockCount": len(blocks), "parseError": error}


@router.delete("/api/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, user: _CurrentUser) -> None:
    doc = _owned_document(doc_id, user)
    storage, tenant_id, key, backend = _storage_binding(doc, user)
    now = datetime.now(UTC).isoformat()
    _set_document_record(
        _PARSED_DOCS_COLLECTION,
        doc_id,
        {"deletionStatus": "deleting", "deletionBackend": backend, "updatedAt": now},
        merge=True,
    )
    try:
        storage.delete(tenant_id, key)
    except Exception as exc:
        log.error("document binary delete failed tenant=%s key=%s: %s", tenant_id, key, exc)
        _set_document_record(
            _PARSED_DOCS_COLLECTION,
            doc_id,
            {"deletionStatus": "failed", "deletionError": str(exc), "updatedAt": datetime.now(UTC).isoformat()},
            merge=True,
        )
        raise HTTPException(status_code=502, detail="Could not delete document binary") from exc

    try:
        _delete_document_record(_PARSED_DOCS_COLLECTION, doc_id)
    except Exception as exc:
        log.error("document metadata delete failed after binary removal for %s: %s", doc_id, exc)
        try:
            _set_document_record(
                _PARSED_DOCS_COLLECTION,
                doc_id,
                {
                    "deletionStatus": "binary_deleted_metadata_pending",
                    "deletionError": str(exc),
                    "updatedAt": datetime.now(UTC).isoformat(),
                },
                merge=True,
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Document binary deleted but metadata cleanup failed") from exc

    folder_id = doc.get("folderId")
    if folder_id:
        try:
            folders_db.update_folder_counts(
                user.uid,
                folder_id,
                doc_delta=-1,
                parsed_delta=-1 if doc.get("parseStatus") == "parsed" else 0,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            log.warning("Failed to decrement folder counts for %s: %s", folder_id, exc)

    log.info("Deleted document %s via %s tenant=%s key=%s", doc_id, backend, tenant_id, key)
