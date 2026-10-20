from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from auth import User, get_current_user
from db.chat_sessions import get_session_index, update_session_fields
from tools.documents.access import DocumentUnavailable, readable_document
from tools.documents.parsing import MAX_DOCUMENTS

router = APIRouter(prefix="/api/sessions", tags=["session-documents"])


class DocumentChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    included: bool = True


class DocumentSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: list[DocumentChoice] = Field(max_length=MAX_DOCUMENTS)


def _owned_session(session_id: str, request: Request):
    idx = get_session_index(session_id)
    if idx is None:
        raise HTTPException(404, "会话不存在。")
    access = request.state.access
    if not access.can_access(idx) or not access.is_owner(idx):
        raise HTTPException(403, "只有会话所有者可以管理附件。")
    return idx


@router.get("/{session_id}/documents")
def get_documents(session_id: str, request: Request, user: User = Depends(get_current_user)) -> dict:  # noqa: B008
    idx = _owned_session(session_id, request)
    documents = []
    for tab in idx.document_tabs:
        try:
            row = readable_document(tab["id"], user_id=user.uid, ready=False)
            documents.append(
                {
                    "id": tab["id"],
                    "included": bool(tab.get("included")),
                    "filename": row.get("originalFilename"),
                    "format": row.get("sourceFormat"),
                    "parseStatus": row.get("parseStatus"),
                    "parseError": row.get("parseError"),
                    "sizeBytes": row.get("sizeBytes"),
                }
            )
        except DocumentUnavailable as exc:
            documents.append(
                {
                    "id": tab["id"],
                    "included": bool(tab.get("included")),
                    "filename": "文件不可用",
                    "format": "",
                    "parseStatus": "failed",
                    "parseError": str(exc),
                }
            )
    return {"documents": documents}


@router.put("/{session_id}/documents")
def save_documents(
    session_id: str,
    body: DocumentSelection,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> dict:
    _owned_session(session_id, request)
    if len({item.id for item in body.documents}) != len(body.documents):
        raise HTTPException(422, "附件列表不能重复。")
    try:
        for item in body.documents:
            readable_document(item.id, user_id=user.uid, ready=False)
    except DocumentUnavailable as exc:
        raise HTTPException(422, str(exc)) from exc
    update_session_fields(
        session_id,
        {
            "documentTabs": [item.model_dump() for item in body.documents],
            "documentIds": [item.id for item in body.documents if item.included],
        },
    )
    return get_documents(session_id, request, user)
