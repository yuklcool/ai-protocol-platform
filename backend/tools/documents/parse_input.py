"""Provider-neutral parse input for newly uploaded document bytes.

Storage and parsing are deliberately separate concerns: the upload route writes
bytes through ``ObjectStorage`` and passes the same bytes here.  AILANG Parse
receives a short-lived local file because its SDK already has a reliable
``parse_file`` path.  No storage provider URI is required.

The historical ``parse_gcs_file`` helper remains available for older call sites
that genuinely start from an existing GCS object.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import PurePosixPath

from tools.documents.ailang_parse import ParseOutcome, _cache_get, _cache_set, _get_client, _parse_file_sync, is_parseable

log = logging.getLogger(__name__)


def _safe_filename(filename: str) -> str:
    value = PurePosixPath(filename.replace("\\", "/")).name.strip()
    return value or "document"


async def parse_uploaded_bytes(
    data: bytes,
    filename: str,
    *,
    output_format: str = "blocks",
) -> ParseOutcome | None:
    """Parse upload bytes without depending on GCS/S3/local-storage semantics.

    Returns ``None`` for unsupported extensions or when AILANG Parse is disabled,
    matching ``parse_gcs_file`` so callers can keep their existing fallback
    behaviour.
    """
    safe_name = _safe_filename(filename)
    if not is_parseable(safe_name):
        log.info("AILANG Parse: skipping uploaded %s (extension not parseable)", safe_name)
        return None
    if _get_client() is None:
        log.info("AILANG Parse: client disabled, skipping uploaded %s", safe_name)
        return None

    digest = hashlib.sha256(data).hexdigest()
    cache_key = f"ailang_parse:{output_format}:sha256:{digest}:{safe_name}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return ParseOutcome(content=cached, output_format=output_format)

    tmp_dir = tempfile.mkdtemp(prefix="ailang_upload_")
    tmp_path = os.path.join(tmp_dir, safe_name)
    try:
        await asyncio.to_thread(_write_bytes, tmp_path, data)
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


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(data)
