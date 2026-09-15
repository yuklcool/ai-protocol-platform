from pathlib import Path

path = Path("backend/adk/agent.py")
text = path.read_text(encoding="utf-8")

old_import = """from config.models import (
    ChainLink,
    active_residency_policy,
    api_name_for,
    entry_for,
    load_models_config,
    provider_for,
)"""
new_import = """from config.models import ChainLink, active_residency_policy, load_models_config
from config.runtime_models import (
    api_name_for,
    entry_for,
    openai_runtime_kwargs,
    provider_for,
    provider_key_missing,
)"""
if old_import not in text:
    raise SystemExit("expected config.models import block not found")
text = text.replace(old_import, new_import, 1)

old_openai = """        kwargs: dict = {}
        api_base = os.environ.get("OPENAI_API_BASE", "").strip()
        if api_base:
            kwargs["api_base"] = api_base
"""
new_openai = """        kwargs: dict = openai_runtime_kwargs(model_id)
"""
if old_openai not in text:
    raise SystemExit("expected OpenAI runtime block not found")
text = text.replace(old_openai, new_openai, 1)

old_keys = """_PROVIDER_KEY_ENVS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def _provider_key_missing(model_ref: str) -> str | None:
    \"\"\"Env var name when a registered/raw provider requires an API key.\"\"\"
    provider = provider_for(model_ref)
    needed = _PROVIDER_KEY_ENVS.get(provider or "")
    if needed is None:
        return None
    return None if os.environ.get(needed) else needed
"""
new_keys = """def _provider_key_missing(model_ref: str) -> str | None:
    \"\"\"Credential hint when a model cannot be used on this deployment.\"\"\"
    return provider_key_missing(model_ref)
"""
if old_keys not in text:
    raise SystemExit("expected provider-key block not found")
text = text.replace(old_keys, new_keys, 1)

path.write_text(text, encoding="utf-8")
