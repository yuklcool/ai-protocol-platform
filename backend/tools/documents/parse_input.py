"""Provider-neutral parse inputs for uploaded documents.

Storage and parsing are deliberately separate concerns. Large uploads are
accepted as file-like objects and copied to the parser's short-lived local file
in bounded chunks; callers do not need to materialise an entire PDF/Office file
as Python bytes. The bytes helper remains for reparse/legacy call sites.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import PurePosixPath
from typing import BinaryIO

from tools.documents.ailang_parse import ParseOutcome, _cache_get, _cache_set, _get_client, _parse_file_sync, is_parseable

log = logging.getLogger(__name__)


def _safe_filename(filename: str) -> str:
    value = PurePosixPath(filename.replace("\\", "/")).name.strip()
    return value or "document"


async def parse_uploaded_fileobj(
    fileobj: BinaryIO,
    filename: str,
    *,
    output_format: str = "blocks",
    chunk_size: int = 1024 * 1024,
) -> ParseOutcome | None:
    """Parse a seekable upload stream without loading it all into memory."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    safe_name = _safe_filename(filename)
    if not is_parseable(safe_name):
        log.info("AILANG Parse: skipping uploaded %s (extension not parseable)", safe_name)
        return None
    if _get_client() is None:
        log.info("AILANG Parse: client disabled, skipping uploaded %s", safe_name)
        return None

    tmp_dir = tempfile.mkdtemp(prefix="ailang_upload_")
    tmp_path = os.path.join(tmp_dir, safe_name)
    try:
        fileobj.seek(0)
        digest = await asyncio.to_thread(_copy_and_hash, fileobj, tmp_path, chunk_size)
        cache_key = f"ailang_parse:{output_format}:sha256:{digest}:{safe_name}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return ParseOutcome(content=cached, output_format=output_format)
        outcome = await asyncio.to_thread(_parse_file_sync, tmp_path, output_format)
        if outcome.ok:
            _cache_set(cache_key, outcome.content)
        return outcome
    except Exception as exc:
        return ParseOutcome(
            error=f"AILANG Parse upload pipeline failed: {type(exc).__name__}: {exc}",
            error_code="unknown",
            output_format=output_format,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def parse_uploaded_bytes(
    data: bytes,
    filename: str,
    *,
    output_format: str = "blocks",
) -> ParseOutcome | None:
    """Compatibility helper for callers that already have the object in memory."""
    from io import BytesIO

    return await parse_uploaded_fileobj(BytesIO(data), filename, output_format=output_format)


def _copy_and_hash(fileobj: BinaryIO, path: str, chunk_size: int) -> str:
    digest = hashlib.sha256()
    with open(path, "wb") as handle:
        while True:
            chunk = fileobj.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            handle.write(chunk)
    return digest.hexdigest()
