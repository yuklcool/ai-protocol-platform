"""ADK FunctionTool registry — maps skill-config tool names to callables.

Model-aware routing:
  - Gemini agents receive ADK built-in tools (VertexAiSearchTool, GoogleSearchTool,
    UrlContextTool) added directly, not via this registry.
  - Claude/OpenAI agents receive AgentTool wrappers created in agent.py.
  - Document tools (list_documents, get_document_content) are the same for all models.
  - Stubs remain for tools not yet ported (code_execution, user_history).

Tools ported in sprint TOOLS-PORTING:
  - list_documents / get_document_content (M1)
  - ai_search / google_search / url_processing (M2, model-aware in agent.py)
  - structured_extraction (M3, registered as after_agent callback, not here)
  - code_execution (M4, model-aware in agent.py)
  - mcp (M5, loaded via mcp/registry.py)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

from google.adk.tools import FunctionTool, ToolContext

from db.persistence import query_documents
from tools.documents.context import build_document_context
from tools.url_processing import url_processing
from tools.workshop_docs import search_workshop_docs

logger = logging.getLogger(__name__)

_PARSED_DOCS_COLLECTION = "parsed_documents"


def _fmt_upload_date(value: object) -> str:
    """Best-effort YYYY-MM-DD from a persisted ``createdAt`` value."""
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%Y-%m-%d")
        except Exception:
            return ""
    s = str(value)
    return s[:10] if len(s) >= 10 and s[4:5] == "-" else ""


async def list_documents(
    skill_id: str | None = None,
    limit: int = 20,
    tool_context: ToolContext = None,
) -> str:
    """List parsed documents available in the workspace.

    Args:
        skill_id: Optional skill ID to filter documents by. Omit to list all your documents.
        limit: Maximum number of documents to return (default 20, max 50).

    Returns:
        A formatted list of document names, IDs, and status.
    """
    user_id = None
    if tool_context is not None:
        user_id = tool_context.state.get("user:id") or tool_context.state.get("user_id")

    filters: list[tuple[str, str, object]] = []
    if user_id:
        filters.append(("userId", "==", user_id))
    if skill_id:
        filters.append(("skillId", "==", skill_id))
    filters.append(("status", "==", "parsed"))

    effective_limit = min(int(limit), 50)

    try:
        docs = await asyncio.to_thread(
            query_documents,
            collection=_PARSED_DOCS_COLLECTION,
            filters=filters,
            order_by="createdAt",
            order_direction="DESCENDING",
            limit=effective_limit,
        )
    except Exception as exc:
        logger.warning("list_documents: persistence query failed: %s", exc)
        return f"Could not retrieve documents: {exc}"

    if not docs:
        return "No documents found in the workspace."

    lines = [
        f"Found {len(docs)} document(s). Refer to them by name (+ upload date to "
        "disambiguate duplicates); do NOT show the [ref] ids to the user:\n"
    ]
    for doc in docs:
        doc_id = doc.get("__id", "?")
        filename = doc.get("originalFilename", "Unknown")
        status = doc.get("status", "unknown")
        fmt = doc.get("sourceFormat", "")
        summary = doc.get("summary") or {}
        blocks_count = summary.get("totalBlocks", 0)
        uploaded = _fmt_upload_date(doc.get("createdAt"))
        parts = [
            p
            for p in (
                fmt or None,
                (f"{blocks_count} blocks" if blocks_count else None),
                (f"uploaded {uploaded}" if uploaded else None),
                (status if status != "parsed" else None),
            )
            if p
        ]
        detail = f" — {', '.join(parts)}" if parts else ""
        lines.append(f"- {filename}{detail} [ref: {doc_id}]")

    return "\n".join(lines)


async def get_document_content(
    doc_id: str,
    section: str | None = None,
    mode: str = "markdown",
    tool_context: ToolContext = None,
) -> str:
    """Get content of a parsed document."""
    try:
        content, blocks = await asyncio.to_thread(build_document_context, doc_id, mode, section)
    except KeyError:
        return f"Document '{doc_id}' not found. Use list_documents to see available documents."
    except Exception as exc:
        logger.warning("get_document_content failed for %s: %s", doc_id, exc)
        return f"Could not load document '{doc_id}': {exc}"

    if mode == "blocks" and blocks is not None and tool_context is not None:
        tool_context.state["temp:document_blocks"] = json.dumps(blocks, ensure_ascii=False)
        tool_context.state["temp:document_id"] = doc_id

    return content


def _extract_ppa_clauses_factory(_config: dict) -> FunctionTool:
    from tools.extract_ppa_clauses import extract_ppa_clauses

    return FunctionTool(extract_ppa_clauses)


def _compare_ppa_contracts_factory(_config: dict) -> FunctionTool:
    from tools.compare_ppa_contracts import compare_ppa_contracts

    return FunctionTool(compare_ppa_contracts)


# tool name → factory function(config dict) → FunctionTool
# Model-aware tools are resolved directly in agent.py. MCP tools are loaded by
# tools/mcp/registry.py and returned as McpToolset.
TOOL_REGISTRY: dict[str, Callable[[dict], FunctionTool]] = {
    "list_documents": lambda _config: FunctionTool(list_documents),
    "get_document_content": lambda _config: FunctionTool(get_document_content),
    "url_processing": lambda _config: FunctionTool(url_processing),
    "search_workshop_docs": lambda _config: FunctionTool(search_workshop_docs),
    "extract_ppa_clauses": _extract_ppa_clauses_factory,
    "compare_ppa_contracts": _compare_ppa_contracts_factory,
}


def get_tool(name: str, config: dict | None = None) -> FunctionTool | None:
    factory = TOOL_REGISTRY.get(name)
    if factory is None:
        logger.warning("Unknown tool requested: %s", name)
        return None
    return factory(config or {})


def list_registered_tools() -> list[str]:
    return sorted(TOOL_REGISTRY)
