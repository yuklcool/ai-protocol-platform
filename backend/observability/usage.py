from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from auth.models import User
from db.persistence import set_document
from observability.llm_metrics import pricing_for_model

COLLECTION = "llm_usage"
log = logging.getLogger(__name__)


def make_usage_callbacks(user: User, skill_id: str) -> tuple[Any, Any]:
    """Count final responses once per model call, including unbudgeted calls."""
    pending: dict[str, tuple[str, str]] = {}

    async def before(context: Any, request: Any) -> None:
        pending[context.invocation_id] = (uuid.uuid4().hex, str(getattr(request, "model", "unknown")))

    async def after(context: Any, response: Any) -> None:
        if getattr(response, "partial", False) is True:
            return
        call = pending.pop(context.invocation_id, None)
        usage = getattr(response, "usage_metadata", None)
        if call is None or usage is None:
            return
        uid = user.uid.strip()
        if not uid:
            return
        input_tokens = getattr(usage, "prompt_token_count", None)
        output_tokens = getattr(usage, "candidates_token_count", None)
        if input_tokens is None or output_tokens is None:
            return
        call_id, model = call
        row = {
            "userId": user.uid,
            "skillId": skill_id,
            "invocationId": context.invocation_id,
            "modelId": model,
            "inputTokens": max(0, int(input_tokens)),
            "outputTokens": max(0, int(output_tokens)),
            "estimatedCostUsd": 0.0,
            "pricingKnown": False,
            "createdAt": time.time(),
        }
        try:
            rates = await asyncio.to_thread(pricing_for_model, model)
            if rates is not None:
                row["estimatedCostUsd"] = (row["inputTokens"] * rates[0] + row["outputTokens"] * rates[1]) / 1_000_000
                row["pricingKnown"] = True
        except Exception:
            log.exception("usage pricing unavailable user=%s call=%s", uid, call_id)
        try:
            await asyncio.to_thread(set_document, COLLECTION, call_id, row)
        except Exception:
            log.exception("usage persistence failed user=%s call=%s", uid, call_id)

    return before, after
