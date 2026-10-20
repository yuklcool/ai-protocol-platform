"""真实上传、Root / AG-UI / ADK 状态传递和模型输入契约;探针模型不调用外部服务。"""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai.types import Content, FunctionCall, Part
from pydantic import Field

from adk.callbacks import make_document_injector
from auth import User, get_current_user
from auth.access_context import build_access_context
from config.platform_config import invalidate_cache
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from observability.user_context import set_user_context
from tools.documents.access import read_attached_document


class InputProbe(BaseLlm):
    model: str = "document-input-probe"
    inputs: list[list[str]] = Field(default_factory=list)
    read_doc_id: str | None = None

    async def generate_content_async(self, llm_request, stream=False) -> AsyncGenerator[LlmResponse, None]:
        self.inputs.append([part.text or "" for content in llm_request.contents for part in (content.parts or [])])
        if self.read_doc_id and len(self.inputs) == 1:
            yield LlmResponse(
                content=Content(
                    role="model",
                    parts=[
                        Part(
                            function_call=FunctionCall(name="read_attached_document", args={"doc_id": self.read_doc_id})
                        )
                    ],
                )
            )
            return
        yield LlmResponse(content=Content(role="model", parts=[Part.from_text(text="已收到本轮输入。")]))


@pytest.fixture()
def stack(monkeypatch, tmp_path):
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("ADK_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    repo = MemoryRepository()
    reset_repository_for_testing(repo)
    invalidate_cache(clear_last_known_good=True)
    actor = {"user": User(uid="same-uid", email="member@local.test")}
    probe = InputProbe()
    from fast_api_app import stream_root_agent
    from protocols.session_bootstrap_routes import router as bootstrap
    from protocols.session_document_routes import router as attachments
    from skills import skill_processor
    from tools.documents.routes import router as documents
    from tools.documents.upload import router as uploads

    monkeypatch.setattr(skill_processor, "_session_service", InMemorySessionService())
    monkeypatch.setattr(
        skill_processor,
        "create_agent_with_thinking",
        lambda *_args, **_kwargs: LlmAgent(
            name="document_probe",
            model=probe,
            tools=[FunctionTool(read_attached_document)],
            before_model_callback=make_document_injector(actor["user"]),
        ),
    )
    from adk.agent_cache import clear

    clear()
    app = FastAPI()
    for router in (uploads, documents, bootstrap, attachments):
        app.include_router(router)
    app.add_api_route("/api/agent/stream", stream_root_agent, methods=["POST"])

    async def identity(request: Request):
        user = actor["user"]
        request.state.access = build_access_context(user)
        set_user_context(user)
        set_user_context(user)
        return user

    app.dependency_overrides[get_current_user] = identity
    with TestClient(app) as client:
        yield client, probe, repo, actor
    clear()
    invalidate_cache(clear_last_known_good=True)
    reset_repository_for_testing(None)


def run(client, ids, *, thread="document-thread", old_state=None):
    return client.post(
        "/api/agent/stream",
        json={
            "threadId": thread,
            "runId": "r",
            "messages": [{"id": "q", "role": "user", "content": "请分析本轮文件并说明依据"}],
            "forwardedProps": {"document_ids": ids},
            "state": old_state or {},
        },
    )


def attached_input(probe):
    return "\n".join(text for text in probe.inputs[-1] if text.startswith("【本轮附件"))


def test_real_upload_selection_clear_and_refresh_recovery_reach_model(stack):
    client, probe, _, _actor = stack
    first = client.post(
        "/api/documents/upload",
        files={"file": ("first.txt", b"UNIQUE-FIRST-119: before 1000, after 620.", "text/plain")},
    )
    second = client.post(
        "/api/documents/upload", files={"file": ("second.csv", b"Road,Value\nUNIQUE-SECOND-119,38\n", "text/csv")}
    )
    assert first.status_code == second.status_code == 200
    a, b = first.json()["docId"], second.json()["docId"]
    assert first.json()["status"] == second.json()["status"] == "parsed"
    assert client.post("/api/sessions/document-thread/bootstrap", json={"skill_id": "root-agent"}).status_code == 200
    response = client.put(
        "/api/sessions/document-thread/documents",
        json={"documents": [{"id": a, "included": True}, {"id": b, "included": False}]},
    )
    assert response.status_code == 200, response.text
    assert run(client, [a]).status_code == 200
    assert probe.inputs and "UNIQUE-FIRST-119" in attached_input(probe)
    assert "UNIQUE-SECOND-119" not in attached_input(probe)
    restored = client.get("/api/sessions/document-thread/documents").json()["documents"]
    assert [(tab["id"], tab["included"]) for tab in restored] == [(a, True), (b, False)]
    response = run(client, [b])
    assert response.status_code == 200, response.text
    assert "UNIQUE-SECOND-119" in attached_input(probe) and "UNIQUE-FIRST-119" not in attached_input(probe)
    response = run(client, [], old_state={"document_ids": [a, b]})
    assert response.status_code == 200, response.text
    assert attached_input(probe) == ""


def test_all_selected_attachments_remain_visible_after_a_real_tool_roundtrip(stack):
    client, probe, _repo, _actor = stack
    first = client.post(
        "/api/documents/upload", files={"file": ("batch.txt", b"UNIQUE-BATCH-119", "text/plain")}
    ).json()
    second = client.post(
        "/api/documents/upload", files={"file": ("values.csv", b"Before,After\n1297,817\n", "text/csv")}
    ).json()
    probe.read_doc_id = first["docId"]

    response = run(client, [first["docId"], second["docId"]])

    assert response.status_code == 200, response.text
    assert "RUN_ERROR" not in response.text
    assert len(probe.inputs) == 2
    for parts in probe.inputs:
        context = "\n".join(text for text in parts if text.startswith("【本轮附件"))
        assert "UNIQUE-BATCH-119" in context
        assert "1297" in context and "817" in context
        assert "batch.txt" in context and "values.csv" in context


def test_same_filename_is_independent_and_user_boundary_stops_model(stack):
    client, probe, repo, actor = stack
    first = client.post("/api/documents/upload", files={"file": ("same.txt", b"FIRST-CONTENT", "text/plain")}).json()
    second = client.post("/api/documents/upload", files={"file": ("same.txt", b"SECOND-CONTENT", "text/plain")}).json()
    assert first["docId"] != second["docId"] and first["storagePath"] != second["storagePath"]
    assert client.get(f"/api/documents/{first['docId']}/download").content == b"FIRST-CONTENT"
    repo.set_document(
        "parsed_documents", first["docId"], {"parseStatus": "failed", "parseError": "无法解析"}, merge=True
    )
    response = run(client, [first["docId"]])
    assert response.status_code == 409 and not probe.inputs and "无法解析" in response.json()["detail"]["message"]
    actor["user"] = actor["user"].model_copy(update={"uid": "another-user"})
    assert client.get(f"/api/documents/{second['docId']}").status_code == 403
    response = run(client, [second["docId"]], thread="other-user")
    assert not probe.inputs and "DOCUMENT_UNAVAILABLE" in response.text
