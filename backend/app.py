"""
Aitana Platform v6 — Root agent definition.

This is the ADK agent entry point. The ADK framework discovers this file
and creates the agent + app from it.

Individual skills create sub-agents; this root agent delegates to them.

Workshop W2a — ADK: The Foundation
  The entire agent is declared here: a name, a model, an instruction, and a
  tool list. No orchestration loop, no retry logic, no token counting. ADK
  handles all of that. Sub-agents are populated at runtime from persisted
  skill configs via the factory in adk/agent.py (W2b).
"""

import os

from google.adk.agents import Agent
from google.adk.apps import App

from adk.agent import resolve_model_chain
from adk.artifact_tools import retrieve_artifact
from adk.session import get_compaction_config
from config.deployment import configure_google_genai_environment, is_managed_gcp_mode
from config.gcp import PLACEHOLDER_PROJECT, resolve_gcp_project
from config.models import api_name_for

# Google GenAI transport is deployment-aware. Managed GCP keeps the historical
# Vertex default; SELF_HOSTED_MODE defaults to the Gemini Developer API and does
# not trigger ADC/project discovery simply by importing this module. An explicit
# GOOGLE_GENAI_USE_VERTEXAI value always wins.
configure_google_genai_environment()

# Only managed-GCP deployments receive the historical project/location defaults.
# A self-host must never be pointed at a fake/placeholder GCP project: optional
# Vertex/GCS providers validate their own project configuration when selected.
if is_managed_gcp_mode():
    _FALLBACK_PROJECT = os.environ.get("PLATFORM_DEFAULT_PROJECT", PLACEHOLDER_PROJECT)
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", resolve_gcp_project() or _FALLBACK_PROJECT)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

# The root agent used to be hard-wired to the `lite` tier, which currently
# resolves to Gemini. That made a formally self-hosted deployment still need a
# Google model even when every Skill used an OpenAI-compatible gateway. Keep
# `lite` as the managed/backward-compatible default, but allow a deployment to
# choose any registered provider model/tier for the root orchestration path.
_ROOT_MODEL_REF = os.environ.get("PLATFORM_DEFAULT_MODEL", "").strip() or "lite"
_ROOT_MODEL_API_NAME = api_name_for(_ROOT_MODEL_REF)


# --- Root agent ---
# The root agent delegates to skill-specific sub-agents.
# In v6, each skill becomes a sub-agent created from its persisted config.

root_agent = Agent(
    name="aitana",
    # Reliability: every provider goes through the shared fallback/retry chain.
    # PLATFORM_DEFAULT_MODEL may be a logical tier or registered model id, so a
    # Self-host can use an OpenAI-compatible gateway without constructing a
    # Gemini/Vertex client on the root path.
    model=resolve_model_chain(_ROOT_MODEL_REF),
    instruction=(
        "You are Aitana, a helpful AI assistant. "
        "You can help with document analysis, search, data extraction, and more. "
        "Use your available tools to assist the user."
    ),
    tools=[retrieve_artifact],  # Tools added dynamically from skill config
    sub_agents=[],  # Sub-agents added dynamically from skill config
)


# G46 M3: org-scoped bucket tools — conditionally attached to the root agent
# when A2A_AGENT_DOCUMENTS_BUCKET is set. Gives peer agents (and the
# orchestrator) the ability to discover + load documents from this deploy's
# bound GCS workspace. Both tools degrade gracefully (return [] / ok=False)
# when the env var is unset OR the SA lacks roles/storage.objectViewer, so
# wiring them unconditionally would also be safe — we gate on env so the
# agent's tool list doesn't grow for deploys that don't use the feature.
if os.environ.get("A2A_AGENT_DOCUMENTS_BUCKET"):
    from tools.org_documents import list_org_documents, read_org_document

    root_agent.tools.extend([list_org_documents, read_org_document])


app = App(
    root_agent=root_agent,
    name="aitana_platform",
    # Compaction follows the same deploy-level root model selection. Per-skill
    # compaction narrowing remains a separate concern, but the App no longer
    # assumes Gemini merely because its historical default tier was `lite`.
    events_compaction_config=get_compaction_config(_ROOT_MODEL_API_NAME),
)
