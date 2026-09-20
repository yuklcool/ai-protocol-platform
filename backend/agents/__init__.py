"""Runtime agent composition.

The public chat surface exposes one Root Agent.  Capabilities are resolved
per turn; this package deliberately does not build a graph of every skill.
"""

from agents.root_runtime import (
    RootCapabilityDenied,
    compose_root_skill,
    resolve_root_capability,
)

__all__ = [
    "RootCapabilityDenied",
    "compose_root_skill",
    "resolve_root_capability",
]
