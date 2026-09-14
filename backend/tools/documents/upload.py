"""Document upload handler — POST /api/documents/upload.

Provider-neutral flow:
  1. Resolve tenant namespace and configured ObjectStorage adapter
  2. Write repository metadata with parseStatus: pending
  3. Store bytes under users/{uid}/docs/{folderId}/{filename}
  4. Parse the uploaded bytes independently of the storage provider
  5. Update repository metadata with parseStatus: parsed|failed + stats
  6. Return ParsedDocumentResponse

Self-hosted deployments therefore need neither GCS nor a signed URL. Cloud GCS
keeps the historical per-client bucket mapping behind ``GcsObjectStorage``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

import db.folders as folders_db
from auth import User, get_current_user
from db.clients import UnmappedTenantError, resolve_documents_bucket
from db.persistence import query_documents, set_document
from object_storage import get_object_storage, object_storage_backend_name
from object_storage.gcs import GcsObjectStorage

_CurrentUser = Annotated[User, Depends(get_current_user)]

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

_COLLECTION = "parsed_documents"

_ALLOWED_EXTENSIONS = {
    ".docx",
    ".pptx",
    ".xlsx",
    ".odt",
    ".odp",
    ".ods",
    ".epub",
    ".eml",
    ".mbox",
    ".html",
    ".htm",
    ".md",
    ".csv",
    ".pdf",
    ".txt",
}

# Canonical Content-Type by extension. This is stored with document metadata so
# download/preview routes do not need to trust a browser supplied value.
_EXTENSION_CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".epub": "application/epub+zip",
    ".eml": "message/rfc822",
    ".mbox": "application/mbox",
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


def _resolve_content_type(filename: str, client_content_type: str | None) -> str:
    ext = PurePosixPath(filename).suffix.lower()
    canonical = _EXTENSION_CONTENT_TYPES.get(ext)
    if canonical:
        return canonical
    return client_content_type or "application/octet-stream"


def _tenant_namespace(user: User) -> str:
    """Use the existing domain tenancy model, with a safe per-user fallback.

    A user without an email/domain must never fall into one global namespace;
    the uid fallback preserves isolation until a real tenant mapping exists.
    """
    domain = (getattr(user, "domain", None) or "").strip().lower()
    if not domain:
        email = (getattr(user, "email", None) or "").strip().lower()
        if "@" in email:
            domain = email.rsplit("@", 1)[1]
    if domain:
        return domain
    return f"user-{user.uid}"


def _storage_for_user(user: User):
    """Return (storage, tenant_namespace, backend_name).

    GCS preserves the pre-existing per-domain bucket resolver. Local storage has
    no provisioning dependency: tenant isolation is the on-disk namespace, so a
    self-host works without any GCS bucket configuration.
    """
    backend = object_storage_backend_name()
    tenant_id = _tenant_namespace(user)
    if backend == "gcs":
        bucket_name = resolve_documents_bucket(user)
        return GcsObjectStorage(bucket_name), tenant_id, backend
    return get_object_storage(), tenant_id, backend


class ParsedDocumentResponse(BaseModel):
    doc_id: str = Field(alias="docId")
    status: str
    original_filename: str = Field(alias="originalFilename")
    blocks_count: int = Field(default=0, alias="blocksCount")
    storage_path: str = Field(alias="storagePath")
    folder_id: str | None = Field(default=None, alias="folderId")
    error: str | None = None

    model_config = {"populate_by_name": True}


# Plain-text formats ailang-parse does NOT handle. These need no external
# parser: decode the upload bytes and emit paragraph blocks directly.
_PLAIN_TEXT_EXTENSIONS = {".txt", ".log", ".text"}


def _is_plain_text(filename: str) -> bool:
    return PurePosixPath(filename).suffix.lower() in _PLAIN_TEXT_EXTENSIONS


def _parse_plain_text(data: bytes) -> list[dict]:
    text = data.decode("utf-8", errors="replace")
    blocks: list[dict] = [
        {"type": "paragraph", "text": para, "block_id": f"p{i}"}
        for i, para in enumerate(chunk.strip() for chunk in text.split("\n\n"))
        if para
    ]
    if not blocks and text.strip():
        blocks = [{"type": "paragraph", "text": text.strip(), "block_id": "p0"}]
    return blocks


async def _run_parse(
    file_bytes: bytes,
    filename: str,
    *,
    source_ref: str,
) -> tuple[str, list, int, str | None]:
    """Run parsing without depending on the object-storage URI scheme."""
    import time

    t0 = time.monotonic()

    if _is_plain_text(filename):
        blocks = _parse_plain_text(file_bytes)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return "parsed", blocks, elapsed_ms, None

    from tools.documents.parse_input import parse_uploaded_bytes

    outcome = await parse_uploaded_bytes(file_bytes, filename, output_format="blocks")
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if outcome is None:
        log.info("AILANG Parse: extension/client unavailable for %s, using AI extraction", source_ref)
        return "pending_ai_extraction", [], elapsed_ms, None
    if not outcome.ok:
        log.error("AILANG Parse failed for %s: [%s] %s", source_ref, outcome.error_code, outcome.error)
        return "failed", [], elapsed_ms, outcome.error

    return "parsed", outcome.blocks or [], elapsed_ms, None


class _ParseResult:
    __slots__ = ("blocks", "error", "parsed_ms", "status")

    def __init__(self, status: str, blocks: list, error: str | None, parsed_ms: int | None) -> None:
        self.status = status
        self.blocks = blocks
        self.error = error
        self.parsed_ms = parsed_ms


def _to_response(doc: dict) -> ParsedDocumentResponse:
    """Build a ParsedDocumentResponse from a parsed_documents-shaped dict."""
    return ParsedDocumentResponse(
        docId=doc.get("__id") or doc.get("doc_id") or doc.get("docId") or "",
        status=doc.get("parseStatus") or doc.get("status") or "parsed",
        originalFilename=doc.get("originalFilename") or "",
        blocksCount=doc.get("blockCount") or len(doc.get("blocks") or []),
        storagePath=doc.get("storagePath") or "",
        folderId=doc.get("folderId"),
        error=doc.get("parseError"),
    )


def _store_document(
    doc_id: str,
    *,
    user_id: str,
    tenant_id: str,
    skill_id: str,
    source_url: str,
    storage_backend: str,
    storage_path: str,
    content_type: str,
    original_filename: str,
    source_format: str,
    folder_id: str | None,
    parse_result: _ParseResult,
    now: datetime,
) -> None:
    pr = parse_result
    blocks = pr.blocks
    doc: dict = {
        "skillId": skill_id,
        "userId": user_id,
        "tenantId": tenant_id,
        "sourceUrl": source_url,
        "sourceFormat": source_format,
        "contentType": content_type,
        "originalFilename": original_filename,
        "storageBackend": storage_backend,
        "storagePath": storage_path,
        "folderId": folder_id,
        "parseStatus": pr.status,
        "blocks": blocks if pr.status == "parsed" else [],
        "blockCount": len(blocks) if pr.status == "parsed" else None,
        "tableCount": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "table") if blocks else None,
        "imageCount": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "image") if blocks else None,
        "changeCount": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "change") if blocks else None,
        "parsedMs": pr.parsed_ms if pr.status == "parsed" else None,
        "parseError": pr.error if pr.status == "failed" else None,
        "status": pr.status,
        "parsedAt": now.isoformat() if pr.status == "parsed" else None,
        "summary": {
            "totalBlocks": len(blocks),
            "headings": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "heading"),
            "tables": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "table"),
            "images": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "image"),
            "changes": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "change"),
        },
        "editedBlocks": {},
        "createdAt": now.isoformat(),
        "updatedAt": now.isoformat(),
    }
    set_document(_COLLECTION, doc_id, doc)
    log.info("Stored ParsedDocument %s (parseStatus=%s, blocks=%d)", doc_id, pr.status, len(blocks))


@router.post("/upload")
async def upload_document(
    user: _CurrentUser,
    file: UploadFile,
    skill_id: str = "",
    folder_id: str = "",
) -> ParsedDocumentResponse:
    """Store a document through ObjectStorage, then parse the uploaded bytes."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a name.")

    ext = PurePosixPath(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {ext!r} is not supported. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    effective_folder_id = folder_id.strip() or folders_db.ensure_default_folder(user.uid)

    try:
        storage, tenant_id, storage_backend = _storage_for_user(user)
    except UnmappedTenantError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "TENANT_NOT_PROVISIONED",
                "message": (
                    "Document upload isn't available for your account. This feature is only "
                    "enabled for organizations that have been set up by an administrator — the "
                    "account you're signed in with isn't mapped to one. If your organization uses "
                    "Aitana, sign in with your work account, or ask an administrator to enable "
                    "document storage for your domain."
                ),
            },
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Object storage is not configured: {exc}") from exc

    safe_filename = file.filename.replace("/", "_").replace("\\", "_")
    content_type = _resolve_content_type(safe_filename, file.content_type)

    existing = query_documents(
        _COLLECTION,
        filters=[
            ("userId", "==", user.uid),
            ("folderId", "==", effective_folder_id),
            ("originalFilename", "==", safe_filename),
        ],
        limit=1,
    )
    is_overwrite = bool(existing)
    doc_id = existing[0]["__id"] if is_overwrite else str(uuid.uuid4())
    if is_overwrite:
        log.info("Re-upload detected for %s — reusing doc_id %s", safe_filename, doc_id)

    storage_path = f"users/{user.uid}/docs/{effective_folder_id}/{safe_filename}"
    now = datetime.now(UTC)

    _store_document(
        doc_id,
        user_id=user.uid,
        tenant_id=tenant_id,
        skill_id=skill_id,
        source_url="",
        storage_backend=storage_backend,
        storage_path=storage_path,
        content_type=content_type,
        original_filename=safe_filename,
        source_format=ext.lstrip("."),
        folder_id=effective_folder_id,
        parse_result=_ParseResult("pending", [], None, None),
        now=now,
    )

    file_bytes = await file.read()
    try:
        object_info = storage.put_bytes(tenant_id, storage_path, file_bytes)
        source_url = object_info.uri
        log.info(
            "Uploaded %s via %s tenant=%s key=%s",
            safe_filename,
            storage_backend,
            tenant_id,
            storage_path,
        )
    except Exception as exc:
        log.error("Object storage upload failed for %s: %s", safe_filename, exc)
        _store_document(
            doc_id,
            user_id=user.uid,
            tenant_id=tenant_id,
            skill_id=skill_id,
            source_url="",
            storage_backend=storage_backend,
            storage_path=storage_path,
            content_type=content_type,
            original_filename=safe_filename,
            source_format=ext.lstrip("."),
            folder_id=effective_folder_id,
            parse_result=_ParseResult("failed", [], str(exc), None),
            now=now,
        )
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {exc}") from exc

    parse_status, blocks, parsed_ms, parse_error = await _run_parse(
        file_bytes,
        safe_filename,
        source_ref=source_url,
    )

    _store_document(
        doc_id,
        user_id=user.uid,
        tenant_id=tenant_id,
        skill_id=skill_id,
        source_url=source_url,
        storage_backend=storage_backend,
        storage_path=storage_path,
        content_type=content_type,
        original_filename=safe_filename,
        source_format=ext.lstrip("."),
        folder_id=effective_folder_id,
        parse_result=_ParseResult(parse_status, blocks, parse_error, parsed_ms),
        now=now,
    )

    if not is_overwrite:
        if parse_status == "parsed":
            try:
                folders_db.update_folder_counts(user.uid, effective_folder_id, doc_delta=1, parsed_delta=1)
            except Exception as exc:
                log.warning("Failed to update folder counts for %s: %s", effective_folder_id, exc)
        elif parse_status not in ("failed",):
            try:
                folders_db.update_folder_counts(user.uid, effective_folder_id, doc_delta=1)
            except Exception as exc:
                log.warning("Failed to update folder counts for %s: %s", effective_folder_id, exc)

    return _to_response(
        {
            "__id": doc_id,
            "parseStatus": parse_status,
            "originalFilename": safe_filename,
            "blockCount": len(blocks),
            "storagePath": storage_path,
            "folderId": effective_folder_id,
        }
    )
