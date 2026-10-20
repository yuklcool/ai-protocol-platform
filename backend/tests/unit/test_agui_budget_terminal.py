"""Verify the real background adapter preserves a callback's typed failure."""

from unittest.mock import AsyncMock

from ag_ui.core import RunAgentInput, UserMessage
from ag_ui_adk.session_manager import SessionManager
from google.adk.agents import Agent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from adk.agui import build_agui_adk_agent, stream_agui_events
from adk.budget_config import BudgetConfig
from adk.run_errors import current_run_error
from auth.models import User
from budget.callback import make_budget_callbacks
from budget.enforcer import BudgetDecision


class NeverCalledModel(BaseLlm):
    async def generate_content_async(self, llm_request, stream=False):
        raise AssertionError("budget must block before calling the model")
        yield


async def test_real_background_adapter_preserves_typed_budget_error():
    SessionManager.reset_instance()
    enforcer = AsyncMock()
    enforcer.consult.return_value = BudgetDecision(
        action="block", remaining_usd=0, period_end=None, message="Tenant quota exhausted", retry_after_seconds=120
    )
    before, _ = make_budget_callbacks(
        enforcer,
        user=User(uid="owner"),
        skill_id="root-agent",
        budget_config=BudgetConfig(identity_key="uid"),
    )
    try:
        agent = Agent(name="root_probe", model=NeverCalledModel(model="local-stub"), before_model_callback=before)
        bridge = build_agui_adk_agent(
            agent,
            user_id="owner",
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
            artifact_service=InMemoryArtifactService(),
        )
        assert bridge._app.events_compaction_config.summarizer._llm is agent.canonical_model
        run = RunAgentInput(
            thread_id="quota-probe",
            run_id="quota-run",
            state={},
            tools=[],
            context=[],
            messages=[UserMessage(id="user-1", content="hello")],
            forwarded_props={},
        )
        events = [event async for event in stream_agui_events(bridge, run, heartbeat_seconds=0)]
        terminal = [event for event in events if event["type"] in ("RUN_FINISHED", "RUN_ERROR")]
        assert terminal == [
            {
                "type": "RUN_ERROR",
                "code": "BUDGET_EXCEEDED",
                "message": "Tenant quota exhausted",
                "retry_after_seconds": 120,
            }
        ]
        assert events[-1] == terminal[0]
        assert current_run_error.get() is None
    finally:
        SessionManager.reset_instance()


class LocalStateModel(BaseLlm):
    async def generate_content_async(self, llm_request, stream=False):
        yield LlmResponse(content=Content(role="model", parts=[Part(text="Applied")]))


async def test_real_background_adapter_escapes_flat_state_keys_for_json_patch():
    SessionManager.reset_instance()
    key = "a2ui_surface:form/~details"

    def write_state(callback_context):
        callback_context.state[key] = {"value": "submitted"}

    try:
        agent = Agent(name="state_probe", model=LocalStateModel(model="local-stub"), before_agent_callback=write_state)
        bridge = build_agui_adk_agent(
            agent,
            user_id="owner",
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
            artifact_service=InMemoryArtifactService(),
        )
        run = RunAgentInput(
            thread_id="state-probe",
            run_id="state-run",
            state={},
            tools=[],
            context=[],
            messages=[UserMessage(id="user-1", content="hello")],
            forwarded_props={},
        )
        events = [event async for event in stream_agui_events(bridge, run, heartbeat_seconds=0)]
        patches = [patch for event in events if event["type"] == "STATE_DELTA" for patch in event["delta"]]
        assert {"op": "add", "path": "/a2ui_surface:form~1~0details", "value": {"value": "submitted"}} in patches
        assert events[-1]["type"] == "RUN_FINISHED"
    finally:
        SessionManager.reset_instance()
