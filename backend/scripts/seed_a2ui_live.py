"""Seed one deterministic A2UI workspace surface into an existing ADK session.

Used only by the live self-host browser acceptance. The browser test creates the
real Skill + session through authenticated product APIs; this helper writes the
same session-state stash that a real tool-result A2UI emitter writes, without
calling an external model.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

from google.adk.events import Event, EventActions

from adk.agui import APP_NAME
from adk.callbacks import A2UI_SURFACE_STATE_PREFIX
from adk.session import get_session_service

CATALOG_ID = "https://a2ui.org/specification/v0_9/basic_catalog.json"
SURFACE_ID = "workspace"


def _messages() -> list[dict]:
    return [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": SURFACE_ID,
                "catalogId": CATALOG_ID,
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": SURFACE_ID,
                "components": [
                    {
                        "id": "root",
                        "component": "Column",
                        "children": ["title", "status", "action"],
                    },
                    {
                        "id": "title",
                        "component": "Text",
                        "text": "A2UI Live Acceptance",
                        "variant": "h2",
                    },
                    {
                        "id": "status",
                        "component": "Text",
                        "text": {"path": "/status"},
                    },
                    {
                        "id": "action",
                        "component": "Button",
                        "child": "action-label",
                        "action": {
                            "event": {
                                "name": "accept_a2ui_live",
                                "context": {
                                    "marker": "A2UI-ACTION-PERSISTED",
                                    "source": "chromium-live-gate",
                                },
                            }
                        },
                    },
                    {
                        "id": "action-label",
                        "component": "Text",
                        "text": "Persist action",
                    },
                ],
            },
        },
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": SURFACE_ID,
                "path": "/",
                "value": {
                    "status": "Rendered from persisted PostgreSQL session state",
                },
            },
        },
    ]


async def _run(user_id: str, session_id: str) -> None:
    service = get_session_service()
    session = await service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise SystemExit(f"ADK session not found: user={user_id} session={session_id}")

    payload = {
        "surfaceId": SURFACE_ID,
        "messages": _messages(),
        "sourceId": f"a2ui-live-seed:{session_id}",
        "toolName": "a2ui_live_acceptance_seed",
        "createdAt": time.time() * 1000,
    }
    state_key = f"{A2UI_SURFACE_STATE_PREFIX}{SURFACE_ID}"
    await service.append_event(
        session,
        Event(
            invocation_id=f"a2ui_live_seed_{int(time.time() * 1000)}",
            author="user",
            actions=EventActions(state_delta={state_key: json.dumps(payload)}),
            timestamp=time.time(),
        ),
    )
    print(json.dumps({"sessionId": session_id, "surfaceId": SURFACE_ID, "stateKey": state_key}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()
    asyncio.run(_run(args.user_id, args.session_id))


if __name__ == "__main__":
    main()
