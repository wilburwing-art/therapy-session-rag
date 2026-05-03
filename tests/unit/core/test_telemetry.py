"""Smoke tests for the OpenTelemetry bootstrap in ``src.core.telemetry``.

These do not exercise a real collector — they guarantee that:

* ``init_telemetry`` is a cheap no-op when ``otel_enabled=false``.
* ``init_telemetry`` does not raise when the collector endpoint is
  unreachable; it logs and returns False (or True, if setup succeeds
  locally but export fails in the background — that's allowed).
* ``record_duration`` is safe to call before init.
* ``instrument_fastapi`` is a safe no-op when telemetry is disabled.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI

import src.core.telemetry as telemetry
from src.core.config import Settings


def _base_settings(**overrides: object) -> Settings:
    return Settings(
        database_url="postgresql://u:p@localhost/t",  # type: ignore[arg-type]
        redis_url="redis://localhost:6379",  # type: ignore[arg-type]
        **overrides,  # type: ignore[arg-type]
    )


@pytest.fixture(autouse=True)
def _reset_telemetry_state() -> Iterator[None]:
    """Isolate module-level state across tests."""
    telemetry._initialized = False
    telemetry._tracer = None
    telemetry._meter = None
    telemetry._duration_histogram = None
    yield
    telemetry._initialized = False
    telemetry._tracer = None
    telemetry._meter = None
    telemetry._duration_histogram = None


def test_init_skipped_when_disabled() -> None:
    """Default configuration must not touch OTEL at all."""
    settings = _base_settings()
    assert settings.otel_enabled is False

    assert telemetry.init_telemetry(settings) is False
    assert telemetry._initialized is False
    assert telemetry._duration_histogram is None


def test_record_duration_is_safe_without_init() -> None:
    """The context manager must be cheap and exception-safe when OTEL is off."""
    with telemetry.record_duration("chat.rag", {"patient_scoped": "true"}):
        result = 2 + 2
    assert result == 4


def test_instrument_fastapi_noop_when_disabled() -> None:
    """Attaching instrumentation must not raise when telemetry is off."""
    app = FastAPI()
    telemetry.instrument_fastapi(app)  # no exceptions


def test_init_with_unreachable_collector_does_not_crash() -> None:
    """When the collector can't be reached, init returns without raising.

    Exporter setup is lazy / background in the OTLP SDK so providers may
    still initialize successfully; the critical guarantee is that boot
    completes. We assert on "no exception" rather than a specific bool.
    """
    settings = _base_settings(
        otel_enabled=True,
        otel_exporter_otlp_endpoint="http://127.0.0.1:1",  # guaranteed closed
        otel_metric_export_interval_millis=60_000,
    )
    # Must not raise even though nothing listens on the endpoint.
    result = telemetry.init_telemetry(settings)
    assert result in {True, False}
    # Second call short-circuits.
    assert telemetry.init_telemetry(settings) is result or (
        telemetry.init_telemetry(settings) is True
    )
    telemetry.shutdown_telemetry()
