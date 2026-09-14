"""Document context builder backed by the provider-neutral repository facade."""

from __future__ import annotations

import json
from typing import Any

from db.persistence import get_document, query_documents

_PARSED_DOCS_COLLECTION = "parsed_documents"


def blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        block_type = block.get("type", "")
        text = block.get("text") or ""
        if block_type == "heading":
            level = max(1, min(6, block.get("level", 1)))
            parts.append(f"{'#' * level} {text}")
        elif block_type in ("paragraph", "text"):
            if text:
                parts.append(text)
        elif block_type == "table":
            headers = block.get("headers") or []
            rows = block.get("rows") or []
            header_texts = [_cell_text(c) for c in headers]
            if header_texts:
                parts.append("| " + " | ".join(header_texts) + " |")
                parts.append("| " + " | ".join(["---"] * len(header_texts)) + " |")
            for row in rows:
                cells = row.get("cells") if isinstance(row, dict) and "cells" in row else row
                parts.append("| " + " | ".join(_cell_text(c) for c in cells or []) + " |")
        elif block_type == "list":
            for i, item in enumerate(block.get("items") or []):
                prefix = f"{i + 1}." if block.get("ordered", False) else "-"
                parts.append(f"{prefix} {item}")
        elif block_type == "change":
            if text:
                change_type = block.get("change_type", "")
                if change_type == "deletion":
                    parts.append(f"~~{text}~~")
                elif change_type == "insertion":
                    parts.append(f"**[INSERTED]** {text}")
                else:
                    parts.append(text)
        elif block_type == "section":
            children = block.get("children") or []
            if children:
                parts.append(blocks_to_markdown(children))
        elif text:
            parts.append(text)
    return "\n\n".join(p for p in parts if p)


def _cell_text(cell: Any) -> str:
    if isinstance(cell, dict):
        return cell.get("text", "")
    return str(cell)


def apply_edits(blocks: list[dict[str, Any]], edited_blocks: dict[str, Any]) -> list[dict[str, Any]]:
    if not edited_blocks:
        return blocks
    result = []
    for i, block in enumerate(blocks):
        edit = edited_blocks.get(str(i))
        if edit:
            edited_text = edit.get("editedText") or edit.get("edited_text")
            if edited_text:
                block = dict(block, text=edited_text)
        result.append(block)
    return result


def list_documents_for_user(user_id: str, skill_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    filters: list[tuple[str, str, Any]] = [("userId", "==", user_id), ("status", "==", "parsed")]
    if skill_id:
        filters.append(("skillId", "==", skill_id))
    return query_documents(
        collection=_PARSED_DOCS_COLLECTION,
        filters=filters,
        order_by="createdAt",
        order_direction="DESCENDING",
        limit=limit,
    )


def build_document_context(
    doc_id: str,
    mode: str = "markdown",
    section: str | None = None,
) -> tuple[str, list[dict[str, Any]] | None]:
    """Load parsed content from the configured repository for agent use."""
    raw = get_document(_PARSED_DOCS_COLLECTION, doc_id)
    if raw is None:
        raise KeyError(f"Document '{doc_id}' not found.")

    original_filename = raw.get("originalFilename", "Unknown document")
    parse_status = raw.get("parseStatus", "pending")
    if parse_status == "failed":
        parse_error = raw.get("parseError") or "unknown error"
        return (
            f"**Document:** {original_filename}\n\n"
            f"⚠️ This document could not be parsed: {parse_error}\n"
            "The document was uploaded but its content is unavailable. "
            "You can tell the user about this error and ask them to re-upload or try a different format."
        ), None
    if parse_status in ("pending", "pending_ai_extraction"):
        return (
            f"**Document:** {original_filename}\n\n"
            f"⏳ This document is still being processed (status: {parse_status}). "
            "Its content is not yet available. Ask the user to try again in a moment."
        ), None

    blocks = apply_edits(raw.get("blocks") or [], raw.get("editedBlocks") or {})
    if section:
        blocks = _filter_by_section(blocks, section)
    if mode == "blocks":
        return json.dumps({"docId": doc_id, "filename": original_filename, "blocks": blocks}, ensure_ascii=False), blocks

    metadata = raw.get("metadata") or {}
    preamble_lines = [f"**Document:** {original_filename}"]
    if metadata.get("title") and metadata["title"] != original_filename:
        preamble_lines.append(f"**Title:** {metadata['title']}")
    if metadata.get("author"):
        preamble_lines.append(f"**Author:** {metadata['author']}")
    if metadata.get("pageCount"):
        preamble_lines.append(f"**Pages:** {metadata['pageCount']}")
    body = blocks_to_markdown(blocks) or raw.get("text", "") or "(No text content extracted.)"
    return f"{'\n'.join(preamble_lines)}\n\n---\n\n{body}", None


def _filter_by_section(blocks: list[dict[str, Any]], section: str) -> list[dict[str, Any]]:
    section_lower = section.lower()
    start_idx = None
    for i, block in enumerate(blocks):
        if block.get("type") == "heading" and section_lower in (block.get("text") or "").lower():
            start_idx = i
            break
    if start_idx is not None:
        result = [blocks[start_idx]]
        for block in blocks[start_idx + 1 :]:
            if block.get("type") == "heading":
                break
            result.append(block)
        return result
    return [block for block in blocks if section_lower in (block.get("text") or "").lower()]
