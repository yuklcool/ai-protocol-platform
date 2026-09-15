"""Document upload handler — POST /api/documents/upload.

The HTTP upload path is bounded-memory: Starlette's spooled UploadFile is streamed
directly into ObjectStorage and then rewound for parsing. New self-host uploads
therefore do not materialise a whole PDF/Office file as Python bytes.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Annotated, BinaryIO
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

import db.folders as folders_db
from auth import User, get_current_user
from db.clients import UnmappedTenantError, resolve_documents_bucket
from db.persistence import query_documents, set_document
from object_storage import get_object_storage, object_storage_backend_name
from object_storage.gcs import GcsObjectStorage, LegacyGcsObjectStorage

_CurrentUser = Annotated[User, Depends(get_current_user)]
log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])
_COLLECTION = "parsed_documents"

_ALLOWED_EXTENSIONS = {
    ".docx", ".pptx", ".xlsx", ".odt", ".odp", ".ods", ".epub", ".eml",
    ".mbox", ".html", ".htm", ".md", ".csv", ".pdf", ".txt",
}
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
_PLAIN_TEXT_EXTENSIONS = {".txt", ".log", ".text"}


def _resolve_content_type(filename: str, client_content_type: str | None) -> str:
    return _EXTENSION_CONTENT_TYPES.get(PurePosixPath(filename).suffix.lower()) or client_content_type or "application/octet-stream"


def _tenant_namespace(user: User) -> str:
    """Return the trusted stable tenant scope for document persistence.

    Explicit ``tenant_id`` wins. ``domain`` is retained only as the legacy
    identity mapping used by pre-Phase-3 accounts; unlike the old implementation
    we never parse an arbitrary email string or invent ``user-<uid>`` as a
    pseudo-tenant. Missing scope fails closed.
    """
    tenant_id = (getattr(user, "tenant_id", None) or getattr(user, "domain", None) or "").strip()
    if not tenant_id:
        raise UnmappedTenantError("Authenticated identity has no stable tenant scope")
    return tenant_id


def _storage_for_user(user: User):
    backend = object_storage_backend_name()
    tenant_id = _tenant_namespace(user)
    if backend == "gcs":
        return GcsObjectStorage(resolve_documents_bucket(user)), tenant_id, backend
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


def _is_plain_text(filename: str) -> bool:
    return PurePosixPath(filename).suffix.lower() in _PLAIN_TEXT_EXTENSIONS


def _parse_plain_text(data: bytes) -> list[dict]:
    from io import BytesIO

    return _parse_plain_text_fileobj(BytesIO(data))


def _parse_plain_text_fileobj(fileobj: BinaryIO) -> list[dict]:
    """Build paragraph blocks line-by-line instead of reading the whole text file."""
    fileobj.seek(0)
    blocks: list[dict] = []
    paragraph_lines: list[str] = []

    def flush() -> None:
        if not paragraph_lines:
            return
        text = "".join(paragraph_lines).strip()
        paragraph_lines.clear()
        if text:
            blocks.append({"type": "paragraph", "text": text, "block_id": f"p{len(blocks)}"})

    for raw_line in fileobj:
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
        if line.strip():
            paragraph_lines.append(line)
        else:
            flush()
    flush()
    return blocks


async def _run_parse_fileobj(
    fileobj: BinaryIO,
    filename: str,
    *,
    source_ref: str,
) -> tuple[str, list, int, str | None]:
    """Parse a seekable upload stream with bounded-memory input handling."""
    import time

    t0 = time.monotonic()
    if _is_plain_text(filename):
        blocks = await asyncio.to_thread(_parse_plain_text_fileobj, fileobj)
        return "parsed", blocks, int((time.monotonic() - t0) * 1000), None

    from tools.documents.parse_input import parse_uploaded_fileobj

    outcome = await parse_uploaded_fileobj(fileobj, filename, output_format="blocks")
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    if outcome is None:
        log.info("AILANG Parse: extension/client unavailable for %s, using AI extraction", source_ref)
        return "pending_ai_extraction", [], elapsed_ms, None
    if not outcome.ok:
        log.error("AILANG Parse failed for %s: [%s] %s", source_ref, outcome.error_code, outcome.error)
        return "failed", [], elapsed_ms, outcome.error
    return "parsed", outcome.blocks or [], elapsed_ms, None


async def _run_parse(
    file_bytes_or_source: bytes | str,
    filename: str | None = None,
    *,
    source_ref: str | None = None,
) -> tuple[str, list, int, str | None]:
    """Compatibility parser for reparse bytes and historical ``gs://`` callers."""
    from io import BytesIO
    import time

    t0 = time.monotonic()
    if isinstance(file_bytes_or_source, str):
        gs_url = file_bytes_or_source
        parsed = urlparse(gs_url)
        if parsed.scheme != "gs" or not parsed.netloc or not parsed.path:
            return "failed", [], 0, "Unsupported document source"
        legacy = LegacyGcsObjectStorage(parsed.netloc)
        key = parsed.path.lstrip("/")
        try:
            file_bytes = legacy.get_bytes("legacy", key)
        except Exception as exc:
            return "failed", [], int((time.monotonic() - t0) * 1000), f"Could not read referenced document: {exc}"
        filename = filename or PurePosixPath(key).name
        source_ref = source_ref or gs_url
    else:
        file_bytes = file_bytes_or_source
        if not filename:
            raise ValueError("filename is required when parsing uploaded bytes")
        source_ref = source_ref or filename

    return await _run_parse_fileobj(BytesIO(file_bytes), filename, source_ref=source_ref)


class _ParseResult:
    __slots__ = ("blocks", "error", "parsed_ms", "status")

    def __init__(self, status: str, blocks: list, error: str | None, parsed_ms: int | None) -> None:
        self.status = status
        self.blocks = blocks
        self.error = error
        self.parsed_ms = parsed_ms


def _to_response(doc: dict) -> ParsedDocumentResponse:
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
    skill_id: str,
    storage_path: str,
    original_filename: str,
    source_format: str,
    folder_id: str | None,
    parse_result: _ParseResult,
    now: datetime,
    tenant_id: str = "",
    source_url: str = "",
    storage_backend: str = "",
    content_type: str = "",
    gs_url: str | None = None,
) -> None:
    if not tenant_id.strip():
        raise PermissionError("stable tenant id is required to store a document")
    if gs_url and not source_url:
        source_url = gs_url
    if not storage_backend and source_url.startswith("gs://"):
        storage_backend = "gcs-legacy"
    if not content_type:
        content_type = _resolve_content_type(original_filename, None)
    pr = parse_result
    blocks = pr.blocks
    doc = {
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


@router.post("/upload")
async def upload_document(
    user: _CurrentUser,
    file: UploadFile,
    skill_id: str = "",
    folder_id: str = "",
) -> ParsedDocumentResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a name.")
    ext = PurePosixPath(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {ext!r} is not supported. Allowed: {sorted(_ALLOWED_EXTENSIONS)}")

    try:
        storage, tenant_id, storage_backend = _storage_for_user(user)
    except UnmappedTenantError as exc:
        raise HTTPException(status_code=403, detail={"code": "TENANT_NOT_PROVISIONED", "message": "Document storage is not provisioned for this organization."}) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Object storage is not configured: {exc}") from exc

    effective_folder_id = folder_id.strip() or folders_db.ensure_default_folder(user.uid, tenant_id=tenant_id)
    if folder_id.strip() and folders_db.get_folder(user.uid, effective_folder_id, tenant_id=tenant_id) is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    safe_filename = file.filename.replace("/", "_").replace("\\", "_")
    content_type = _resolve_content_type(safe_filename, file.content_type)
    existing = query_documents(
        _COLLECTION,
        filters=[
            ("tenantId", "==", tenant_id),
            ("userId", "==", user.uid),
            ("folderId", "==", effective_folder_id),
            ("originalFilename", "==", safe_filename),
        ],
        limit=1,
    )
    is_overwrite = bool(existing)
    doc_id = existing[0]["__id"] if is_overwrite else str(uuid.uuid4())
    storage_path = f"users/{user.uid}/docs/{effective_folder_id}/{safe_filename}"
    now = datetime.now(UTC)
    base = dict(
        user_id=user.uid,
        tenant_id=tenant_id,
        skill_id=skill_id,
        storage_backend=storage_backend,
        storage_path=storage_path,
        content_type=content_type,
        original_filename=safe_filename,
        source_format=ext.lstrip("."),
        folder_id=effective_folder_id,
        now=now,
    )
    _store_document(doc_id, source_url="", parse_result=_ParseResult("pending", [], None, None), **base)

    try:
        await file.seek(0)
        object_info = await asyncio.to_thread(storage.put_fileobj, tenant_id, storage_path, file.file)
        source_url = object_info.uri
    except Exception as exc:
        _store_document(doc_id, source_url="", parse_result=_ParseResult("failed", [], str(exc), None), **base)
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {exc}") from exc

    await file.seek(0)
    parse_status, blocks, parsed_ms, parse_error = await _run_parse_fileobj(file.file, safe_filename, source_ref=source_url)
    _store_document(doc_id, source_url=source_url, parse_result=_ParseResult(parse_status, blocks, parse_error, parsed_ms), **base)

    if not is_overwrite:
        try:
            if parse_status == "parsed":
                folders_db.update_folder_counts(
                    user.uid,
                    effective_folder_id,
                    doc_delta=1,
                    parsed_delta=1,
                    tenant_id=tenant_id,
                )
            elif parse_status != "failed":
                folders_db.update_folder_counts(
                    user.uid,
                    effective_folder_id,
                    doc_delta=1,
                    tenant_id=tenant_id,
                )
        except Exception as exc:
            log.warning("Failed to update folder counts for %s: %s", effective_folder_id, exc)

    return _to_response({
        "__id": doc_id,
        "parseStatus": parse_status,
        "originalFilename": safe_filename,
        "blockCount": len(blocks),
        "storagePath": storage_path,
        "folderId": effective_folder_id,
    })