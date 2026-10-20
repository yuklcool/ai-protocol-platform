"""
OpenTelemetry setup for Aitana Platform.

ADK exports traces via OTEL natively. This configures:
  - GCS upload for prompt/response logging
  - Cloud Trace integration
  - Langfuse v3 OTEL ingestion (future)
"""

import logging
import os

from observability.trace_export import install_trace_export


def setup_telemetry() -> str | None:
    """Configure OpenTelemetry and GenAI telemetry with GCS upload."""

    # Silence noisy OTEL exporters that spam the log with connection-refused
    # tracebacks when the local collector isn't running. Real app errors should
    # never be buried under OTEL retry noise.
    for noisy in (
        "opentelemetry.exporter.otlp",
        "opentelemetry.sdk.trace.export",
        "opentelemetry.sdk.metrics.export",
    ):
        logging.getLogger(noisy).setLevel(logging.CRITICAL)

    # Install the SDK TracerProvider + Cloud Trace exporter FIRST (issue #39).
    # HAS add_span_processor, and the OTel default (ProxyTracerProvider) does
    # not. ADK never installed one, so for the platform's whole life that
    # wire-up silently no-op'd and every span ADK emitted was dropped — Cloud
    # Trace held 2 traces for test across seven days.
    install_trace_export()

    # Sprint 2.14 — register UserAttributeSpanProcessor on whichever
    # TracerProvider is active. Now that install_trace_export() has run this
    # normally succeeds; it stays best-effort for forks that disable export.
    _attach_user_span_processor()

    bucket = os.environ.get("LOGS_BUCKET_NAME")
    capture_content = os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")
    if bucket and capture_content != "false":
        logging.info("Prompt-response logging enabled - mode: NO_CONTENT (metadata only)")
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "NO_CONTENT"
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT", "jsonl")
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK", "upload")
        os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
        commit_sha = os.environ.get("COMMIT_SHA", "dev")
        os.environ.setdefault(
            "OTEL_RESOURCE_ATTRIBUTES",
            f"service.namespace=aitana-platform,service.version={commit_sha}",
        )
        path = os.environ.get("GENAI_TELEMETRY_PATH", "completions")
        os.environ.setdefault(
            "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH",
            f"gs://{bucket}/{path}",
        )
    else:
        logging.info(
            "Prompt-response logging disabled "
            "(set LOGS_BUCKET_NAME and OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT to enable)"
        )

    return bucket


def _attach_user_span_processor() -> None:
    """Register UserAttributeSpanProcessor on the active TracerProvider.

    Sprint 2.14. Best-effort: the default OTel ProxyTracerProvider does
    NOT have ``add_span_processor`` — only the SDK ``TracerProvider``
    does. ADK + the GenAI auto-instrumentation typically install a
    real SDK provider before this runs. If they don't, we log a
    warning and continue — span attribution is a nice-to-have, not
    a correctness requirement.
    """
    from opentelemetry import trace as otel_trace

    from observability.user_span_processor import UserAttributeSpanProcessor

    provider = otel_trace.get_tracer_provider()
    add_span_processor = getattr(provider, "add_span_processor", None)
    if add_span_processor is None:
        logging.info(
            "user attribution: TracerProvider is %s — no add_span_processor; "
            "spans will not carry user.* attrs. (Forks needing user attribution "
            "in environments without ADK auto-instrumentation should set up their "
            "own SDK TracerProvider before calling setup_telemetry.)",
            type(provider).__name__,
        )
        return
    add_span_processor(UserAttributeSpanProcessor())
    logging.info("user attribution: UserAttributeSpanProcessor registered on %s", type(provider).__name__)
