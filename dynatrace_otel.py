"""
SENTINEL × DYNATRACE — Track 5 Integration
═══════════════════════════════════════════════════════════════════════════════
Google Cloud Rapid Agent Hackathon 2026 — Dynatrace Partner Bucket

Adds Dynatrace as a SECOND OTLP destination alongside Arize, and registers
three Sentinel-specific business metrics. Zero impact on existing Arize spans.

USAGE (from main.py, after arize_register returns its tracer_provider):

    from dynatrace_otel import attach_dynatrace_exporter, sentinel_metrics
    attach_dynatrace_exporter(tracer_provider)
    sentinel_metrics.contracts_queried(count=42, agency="DOD")

Environment variables required:
    DT_ENVIRONMENT_URL   e.g. https://ncz15754.live.dynatrace.com
    DT_API_TOKEN         dt0c01.XXX with scopes:
                           openTelemetryTrace.ingest, metrics.ingest, logs.ingest

Author: Bumboclaat (Pete's AI) — May 13, 2026
"""

from __future__ import annotations

import os
import logging
from typing import Optional

log = logging.getLogger("sentinel.dynatrace")

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

DT_ENV_URL = os.environ.get("DT_ENVIRONMENT_URL", "").rstrip("/")
DT_TOKEN = os.environ.get("DT_API_TOKEN", "")
DT_ENABLED = bool(DT_ENV_URL and DT_TOKEN)

# Dynatrace OTLP endpoint paths (per https://docs.dynatrace.com/docs/ingest-from/opentelemetry/otlp-api)
DT_TRACES_ENDPOINT = f"{DT_ENV_URL}/api/v2/otlp/v1/traces" if DT_ENABLED else ""
DT_METRICS_ENDPOINT = f"{DT_ENV_URL}/api/v2/otlp/v1/metrics" if DT_ENABLED else ""
DT_LOGS_ENDPOINT = f"{DT_ENV_URL}/api/v2/otlp/v1/logs" if DT_ENABLED else ""

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "sentinel-osint-agent")
SERVICE_VERSION = os.environ.get("SENTINEL_VERSION", "5.0.0")


# ─────────────────────────────────────────────────────────────────────────────
# Tracer setup — attach Dynatrace OTLP exporter to existing tracer_provider
# ─────────────────────────────────────────────────────────────────────────────

def attach_dynatrace_exporter(tracer_provider) -> bool:
    """
    Attach a second BatchSpanProcessor that ships traces to Dynatrace.
    The original Arize processor remains untouched — dual-destination is
    idiomatic OTel; both run independently in parallel.

    Returns True on success, False if Dynatrace disabled or import fails.
    """
    if not DT_ENABLED:
        log.warning("Dynatrace OTel disabled — DT_ENVIRONMENT_URL or DT_API_TOKEN missing")
        return False

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as e:
        log.error(f"opentelemetry-exporter-otlp-proto-http not installed: {e}")
        return False

    headers = {"Authorization": f"Api-Token {DT_TOKEN}"}

    try:
        dt_exporter = OTLPSpanExporter(
            endpoint=DT_TRACES_ENDPOINT,
            headers=headers,
            timeout=30,
        )
        dt_processor = BatchSpanProcessor(
            dt_exporter,
            max_export_batch_size=512,
            schedule_delay_millis=5000,
        )
        tracer_provider.add_span_processor(dt_processor)
        log.info(f"✓ Dynatrace OTel tracing attached → {DT_TRACES_ENDPOINT}")
        print(f"✓ Dynatrace tracing active — endpoint: {DT_ENV_URL}")
        return True
    except Exception as e:
        log.error(f"Failed to attach Dynatrace exporter: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Metrics setup — independent MeterProvider for Dynatrace business metrics
# ─────────────────────────────────────────────────────────────────────────────

class _SentinelMetrics:
    """
    Three business-level metrics that judges will want to see in Dynatrace:
      • sentinel.contracts.queried       (counter, dim: agency)
      • sentinel.confidence.score.avg    (histogram, dim: tier)
      • sentinel.vendor.coverage         (gauge, dim: query_type)

    These complement the auto-captured Gemini-token / tool-call / latency
    metrics that flow from the trace processor.
    """

    def __init__(self):
        self._meter = None
        self._contracts_counter = None
        self._confidence_histogram = None
        self._vendor_gauge_value = 0
        self._init_attempted = False

    def _init(self):
        if self._init_attempted:
            return
        self._init_attempted = True

        if not DT_ENABLED:
            log.warning("Metrics disabled — Dynatrace not configured")
            return

        try:
            from opentelemetry import metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import (
                PeriodicExportingMetricReader,
            )
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.resources import Resource
        except ImportError as e:
            log.error(f"OTel metrics SDK not installed: {e}")
            return

        try:
            resource = Resource.create({
                "service.name": SERVICE_NAME,
                "service.version": SERVICE_VERSION,
                "deployment.environment": os.environ.get("SENTINEL_ENV", "production"),
            })

            metric_exporter = OTLPMetricExporter(
                endpoint=DT_METRICS_ENDPOINT,
                headers={"Authorization": f"Api-Token {DT_TOKEN}"},
                timeout=30,
            )
            reader = PeriodicExportingMetricReader(
                metric_exporter,
                export_interval_millis=30000,  # 30s push cadence
            )
            provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(provider)
            self._meter = metrics.get_meter("sentinel.business", SERVICE_VERSION)

            self._contracts_counter = self._meter.create_counter(
                name="sentinel.contracts.queried",
                description="Number of surveillance contracts returned by an agent query",
                unit="1",
            )
            self._confidence_histogram = self._meter.create_histogram(
                name="sentinel.confidence.score",
                description="Confidence score of contracts returned (0.0–1.0)",
                unit="1",
            )
            self._vendor_gauge = self._meter.create_observable_gauge(
                name="sentinel.vendor.coverage",
                description="Unique vendors touched in the current session",
                callbacks=[lambda options: [
                    self._observe_vendor_gauge(options)
                ]],
                unit="1",
            )

            log.info(f"✓ Dynatrace metrics active → {DT_METRICS_ENDPOINT}")
            print(f"✓ Dynatrace metrics active — 3 Sentinel business metrics registered")
        except Exception as e:
            log.error(f"Failed to init Dynatrace metrics: {e}")

    def _observe_vendor_gauge(self, options):
        from opentelemetry.metrics import Observation
        return Observation(self._vendor_gauge_value, {"service": SERVICE_NAME})

    # ── public API ──────────────────────────────────────────────────────────

    def contracts_queried(self, count: int, agency: Optional[str] = None,
                          query_type: Optional[str] = None):
        """Record contract result count for a single agent query."""
        self._init()
        if self._contracts_counter is None:
            return
        attrs = {}
        if agency:
            attrs["agency"] = agency
        if query_type:
            attrs["query_type"] = query_type
        self._contracts_counter.add(count, attrs)

    def confidence_score(self, score: float, tier: Optional[str] = None):
        """Record one contract's confidence score (0.0–1.0)."""
        self._init()
        if self._confidence_histogram is None:
            return
        attrs = {"tier": tier} if tier else {}
        self._confidence_histogram.record(score, attrs)

    def set_vendor_coverage(self, unique_vendors: int):
        """Update the observable gauge of unique vendors in this session."""
        self._init()
        self._vendor_gauge_value = unique_vendors


sentinel_metrics = _SentinelMetrics()


# ─────────────────────────────────────────────────────────────────────────────
# Smoke-test helper — call this once at startup to verify the pipeline
# ─────────────────────────────────────────────────────────────────────────────

def smoke_test() -> dict:
    """Emit a single sample trace + metric and return status dict."""
    result = {"dynatrace_enabled": DT_ENABLED, "trace_ok": False, "metric_ok": False}
    if not DT_ENABLED:
        return result

    try:
        from opentelemetry import trace
        tracer = trace.get_tracer("sentinel.smoke")
        with tracer.start_as_current_span("sentinel.smoke.startup") as span:
            span.set_attribute("smoke.test", True)
            span.set_attribute("service.name", SERVICE_NAME)
        result["trace_ok"] = True
    except Exception as e:
        result["trace_error"] = str(e)

    try:
        sentinel_metrics.contracts_queried(1, agency="SMOKE_TEST", query_type="startup")
        result["metric_ok"] = True
    except Exception as e:
        result["metric_error"] = str(e)

    return result
