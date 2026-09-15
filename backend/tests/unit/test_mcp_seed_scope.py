"""Built-in MCP scopes and conservative legacy seed migration."""
from unittest.mock import MagicMock, patch

import pytest

from scripts import seed_mcp_servers as seeds


@pytest.mark.parametrize("name", [
    "EXT_APPS_MAP_CONFIG", "TOOLBOX_CONFIG", "TOOLBOX_ONE_BQ_CONFIG", "MAPS_GROUNDING_CONFIG",
])
def test_builtin_configs_are_explicitly_platform_shared(name):
    assert getattr(seeds, name)["scope"] == "platform"


@pytest.mark.parametrize("scope", [None, "tenant", "platform"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_reseed_preserves_endpoint_credentials_and_explicit_scope(scope, dry_run):
    existing = {"url": "https://deployed.example/mcp", "headers": {"secret": "private"}}
    if scope:
        existing.update(scope=scope, tenantId="tenant-a")
    store = MagicMock()
    store.get_document.return_value = existing
    with patch.object(seeds, "fs", store):
        seeds.seed_ext_apps_map(None, dry_run=dry_run)
    if scope is None and not dry_run:
        store.set_document.assert_called_once_with(
            "mcp_servers", "ext-apps-map", {**existing, "scope": "platform"},
        )
    else:
        store.set_document.assert_not_called()
