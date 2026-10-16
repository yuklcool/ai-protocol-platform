"""Authenticated effective Root Agent metadata for production Chat."""

from fastapi import APIRouter, Depends, HTTPException, Request

from agents.root_runtime import RootCapabilityDenied, compose_root_skill, effective_root_config, resolve_root_capability
from auth import User, get_current_user
from config.platform_config import PlatformConfigUnavailable, get_platform_config
from skills.routes import SkillResponse

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("")
@router.get("/capabilities/{capability_ref}")
def get_agent_metadata(
    request: Request,
    capability_ref: str = "root-agent",
    user: User = Depends(get_current_user),  # noqa: B008
) -> SkillResponse:
    try:
        config = effective_root_config(get_platform_config().agent, request.state.access.tenant_id)
        skill = resolve_root_capability(config, user, request.state.access, capability_ref)
    except PlatformConfigUnavailable as exc:
        raise HTTPException(503, "Root Agent policy is temporarily unavailable") from exc
    except RootCapabilityDenied as exc:
        raise HTTPException(404, "Root Agent capability is not available") from exc
    runtime = compose_root_skill(skill, config)
    # Public runtime metadata does not expose the Agent's system instructions.
    runtime.instructions = ""
    runtime.references = {}
    runtime.assets = {}
    return SkillResponse.from_config(runtime)
