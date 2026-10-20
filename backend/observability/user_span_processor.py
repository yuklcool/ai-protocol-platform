"""Attach verified user attribution to OTel spans."""

from __future__ import annotations

from typing import Any

from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

from observability.user_context import get_user_context


class UserAttributeSpanProcessor(SpanProcessor):
    """Stamps every started span with the current task's user attrs.

    Standard OTel SpanProcessor — no surprises. Implements all four
    contract methods. ``on_start`` is where the work happens; the
    other three are no-ops or trivially-true returns.
    """

    def on_start(self, span: Span, parent_context: Any = None) -> None:
        attrs = get_user_context()
        if not attrs:
            return
        for key, value in attrs.items():
            span.set_attribute(key, value)

    def on_end(self, span: ReadableSpan) -> None:
        # No-op: user attrs are set at start; end is too late to
        # influence what the exporter sees on a synchronous flush.
        return

    def shutdown(self) -> None:
        return

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
