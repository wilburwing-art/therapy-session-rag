"""OpenTelemetry bootstrap and typed helpers.

Telemetry is opt-in. When ``otel_enabled=false`` (the default) nothing
is imported from the OTEL SDK beyond the no-op API shims, no exporters
are registered, no network calls are made, and ``record_duration`` /
``start_span`` become cheap no-ops. This keeps local dev, CI, and
production-without-collector paths free of external dependencies.

Design goals:

* Import failures in the OTEL SDK must never break the app. Every
  exporter / instrumentation call is guarded.
* A single ``record_duration`` context manager is exposed to business
  code so services don't import OTEL directly and can't accidentally
  crash when the collector is unreachable.
* FastAPI / SQLAlchemy / httpx / Redis instrumentation is attached only
  when the app is available and OTEL is enabled.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from src.core.config import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Module-level state; set once on init.
_initialized: bool = False
_tracer: Any | None = None
_meter: Any | None = None
_duration_histogram: Any | None = None

# Reusable bucket boundaries (seconds) for latency histograms. Covers
# sub-10ms DB lookups up to ~5min LLM calls.
_DURATION_BUCKETS_SECONDS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    300.0,
)


def init_telemetry(settings: Settings, app: FastAPI | None = None) -> bool:
    """Initialize OpenTelemetry if ``settings.otel_enabled`` is true.

    Returns ``True`` when telemetry was activated, ``False`` otherwise.
    Safe to call more than once — subsequent calls are no-ops.

    Any import or collector error is caught and logged. The app never
    fails to boot because telemetry could not start.
    """
    global _initialized, _tracer, _meter, _duration_histogram

    if _initialized:
        return True

    if not settings.otel_enabled:
        logger.info("OpenTelemetry disabled (otel_enabled=false)")
        return False

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    except ImportError as exc:
        logger.warning("OpenTelemetry SDK import failed; telemetry disabled: %s", exc)
        return False

    try:
        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": "0.1.0",
                "deployment.environment": settings.app_env,
            }
        )

        # Traces
        sampler = ParentBased(root=TraceIdRatioBased(settings.otel_traces_sample_rate))
        tracer_provider = TracerProvider(resource=resource, sampler=sampler)
        span_exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=settings.otel_exporter_otlp_insecure,
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)

        # Metrics
        metric_exporter = OTLPMetricExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=settings.otel_exporter_otlp_insecure,
        )
        metric_reader = PeriodicExportingMetricReader(
            exporter=metric_exporter,
            export_interval_millis=settings.otel_metric_export_interval_millis,
        )
        views = [
            View(
                instrument_name="therapyrag.*.duration",
                aggregation=ExplicitBucketHistogramAggregation(
                    boundaries=_DURATION_BUCKETS_SECONDS
                ),
            )
        ]
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
            views=views,
        )
        metrics.set_meter_provider(meter_provider)

        _tracer = trace.get_tracer("therapyrag")
        _meter = metrics.get_meter("therapyrag")
        _duration_histogram = _meter.create_histogram(
            name="therapyrag.operation.duration",
            unit="s",
            description="Duration of instrumented business operations in seconds.",
        )
    except Exception as exc:  # noqa: BLE001 - telemetry must never crash boot
        logger.warning("OpenTelemetry provider setup failed; telemetry disabled: %s", exc)
        return False

    _initialized = True

    if app is not None:
        instrument_fastapi(app)

    _instrument_libraries()

    logger.info(
        "OpenTelemetry initialized (endpoint=%s, service=%s, sample_rate=%.2f)",
        settings.otel_exporter_otlp_endpoint,
        settings.otel_service_name,
        settings.otel_traces_sample_rate,
    )
    return True


def instrument_fastapi(app: FastAPI) -> None:
    """Attach FastAPI instrumentation to an app instance.

    Safe to call when telemetry is disabled — it becomes a no-op. Any
    instrumentation error is logged, not raised.
    """
    if not _initialized:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FastAPI OTEL instrumentation failed: %s", exc)


def _instrument_libraries() -> None:
    """Attach SQLAlchemy / httpx / Redis instrumentation best-effort."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
    except Exception as exc:  # noqa: BLE001
        logger.debug("SQLAlchemy OTEL instrumentation skipped: %s", exc)
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # noqa: BLE001
        logger.debug("httpx OTEL instrumentation skipped: %s", exc)
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Redis OTEL instrumentation skipped: %s", exc)


@contextmanager
def record_duration(
    operation: str,
    attributes: dict[str, str] | None = None,
) -> Iterator[None]:
    """Record wall-clock duration of a block of code.

    Always safe to call — if OTEL isn't initialized this is a no-op,
    and any exporter / provider error is swallowed so business logic
    continues uninterrupted.

    Usage::

        with record_duration("chat.rag", {"patient_scoped": "true"}):
            ...
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        histogram = _duration_histogram
        if histogram is not None:
            try:
                attrs: dict[str, str] = {"operation": operation}
                if attributes:
                    attrs.update(attributes)
                histogram.record(elapsed, attributes=attrs)
            except Exception as exc:  # noqa: BLE001
                logger.debug("OTEL record_duration swallowed error: %s", exc)


def shutdown_telemetry() -> None:
    """Flush and shut down OTEL providers. Safe to call when disabled."""
    if not _initialized:
        return
    try:
        from opentelemetry import metrics, trace

        tracer_provider = trace.get_tracer_provider()
        shutdown = getattr(tracer_provider, "shutdown", None)
        if callable(shutdown):
            shutdown()
        meter_provider = metrics.get_meter_provider()
        shutdown = getattr(meter_provider, "shutdown", None)
        if callable(shutdown):
            shutdown()
    except Exception as exc:  # noqa: BLE001
        logger.debug("OTEL shutdown swallowed error: %s", exc)
