"""附件读取在模型调用之前检查身份、租户、解析状态和当前轮次选择。"""

from google.adk.tools import ToolContext

from db.persistence import get_document
from tools.documents.parsing import MAX_DOCUMENTS


class DocumentUnavailable(ValueError):
    pass


def readable_document(doc_id: str, *, user_id: str, tenant_id: str, ready: bool = True) -> dict:
    row = get_document("parsed_documents", doc_id)
    if not row or not tenant_id or row.get("tenantId") != tenant_id or row.get("userId") != user_id:
        raise DocumentUnavailable("所选文件不存在或当前账号无权读取,请移除后重新选择。")
    if row.get("deletionStatus"):
        raise DocumentUnavailable("文件正在删除或已不可用,请移除后重新选择。")
    if ready and (row.get("parseStatus") != "parsed" or not row.get("blocks")):
        name = row.get("originalFilename") or "所选文件"
        reason = row.get("parseError") or "解析尚未完成,请等待或重新解析。"
        raise DocumentUnavailable(f"{name} 暂不可分析:{reason}")
    return row


def validate_selection(ids: list[str], *, user_id: str, tenant_id: str) -> list[str]:
    if len(ids) > MAX_DOCUMENTS:
        raise DocumentUnavailable(f"每轮最多分析 {MAX_DOCUMENTS} 个文件,请减少选择。")
    result = list(dict.fromkeys(ids))
    for doc_id in result:
        readable_document(doc_id, user_id=user_id, tenant_id=tenant_id)
    return result


def document_text(row: dict) -> str:
    from tools.documents.context import apply_edits, blocks_to_markdown

    return "\n\n".join(
        f"【{row.get('originalFilename', '文件')} · {block.get('source') or block.get('block_id') or index}】\n"
        + blocks_to_markdown([block])
        for index, block in enumerate(apply_edits(row.get("blocks") or [], row.get("editedBlocks") or {}), 1)
    )


def read_attached_document(doc_id: str, offset: int = 0, limit: int = 12000, tool_context: ToolContext = None) -> dict:
    """分页读取本轮选择的附件;引用返回的文件名与位置,hasMore 为真时继续读取。"""
    from observability.tenant_context import get_tenant_context

    identity = get_tenant_context() or {}
    if tool_context is None or doc_id not in (tool_context.state.get("document_ids") or []):
        raise DocumentUnavailable("此文件未被选为本轮附件,不能读取。")
    row = readable_document(doc_id, user_id=identity.get("tenant.uid", ""), tenant_id=identity.get("tenant.id", ""))
    text = document_text(row)
    start = min(len(text), max(0, int(offset)))
    end = min(start + max(1, min(int(limit), 24000)), len(text))
    return {
        "docId": doc_id,
        "filename": row.get("originalFilename"),
        "text": text[start:end],
        "offset": start,
        "nextOffset": end,
        "totalCharacters": len(text),
        "hasMore": end < len(text),
    }
