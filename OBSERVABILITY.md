# Observability

TherapyRAG emits OpenTelemetry traces and metrics. Telemetry is **opt-in**:
with `OTEL_ENABLED=false` (the default) nothing is exported, no connections
are opened, and the app runs with zero OTEL overhead. That's the mode
used by CI and local dev-without-the-stack.

When you want to see signals, run the local stack and flip the flag.

## Quickstart

```bash
# 1. Start the local observability stack alongside the main infra.
docker compose \
  -f docker-compose.yml \
  -f docker-compose.observability.yml \
  up -d

# 2. Point the API at the collector.
cat >> .env <<'EOF'
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=therapyrag-api
EOF

# 3. Restart the API / workers so the new env is picked up.
uv run uvicorn src.main:app --reload

# 4. Open the dashboard.
open http://localhost:3001   # Grafana → TherapyRAG → Core signals
```

Admin login is `admin` / `admin` (anonymous viewers also have read-only
access to every dashboard, so you can share screenshots without handing
over a password).

## What you get

| Component | Port | What it does |
|-----------|------|--------------|
| OTEL Collector | 4317 (gRPC), 4318 (HTTP) | Accepts OTLP from the app, scrubs PHI-shaped attributes, fans out to Tempo (traces) and Prometheus (metrics). |
| Prometheus | 9090 | 7-day retention of metrics scraped from the collector at :8889. |
| Tempo | 3200 | Trace storage — searchable from Grafana's Explore tab. |
| Grafana | 3001 | UI. Datasources and dashboards are auto-provisioned from `infra/observability/grafana/`. |

## Instrumentation

Automatic (via OTEL contrib packages):

- **FastAPI** — HTTP server spans, request duration histograms by route
  and status code.
- **SQLAlchemy** — DB statement spans (statement text is stripped by the
  collector before export; see `otel-collector-config.yaml`).
- **httpx** — outbound HTTP client spans (used for Deepgram, OpenAI,
  Anthropic, Stripe).
- **Redis** — command spans.

Manual duration metrics (business operations):

- `therapyrag.operation.duration{operation="chat.rag"}` — end-to-end
  patient chat turn: guardrails, embedding, vector search, Claude.
- `therapyrag.operation.duration{operation="summarization.recap"}` —
  the Claude call that turns a transcript into a structured recap.
- `therapyrag.operation.duration{operation="worker.transcription"}` —
  Deepgram transcription job, per-session.

Each is a histogram with buckets from 5ms to 5min, exposed in
Prometheus as `therapyrag_operation_duration_seconds_*`.

## Common queries

Grafana Explore → Prometheus:

```promql
# p95 chat latency
histogram_quantile(
  0.95,
  sum by (le) (rate(therapyrag_operation_duration_seconds_bucket{operation="chat.rag"}[5m]))
)

# recap throughput per minute
sum(rate(therapyrag_operation_duration_seconds_count{operation="summarization.recap"}[5m])) * 60

# 5xx error rate on the API
sum(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[5m]))
 / clamp_min(sum(rate(http_server_request_duration_seconds_count[5m])), 1)

# slowest route over the last hour, p95
topk(5,
  histogram_quantile(
    0.95,
    sum by (le, http_route) (rate(http_server_request_duration_seconds_bucket[1h]))
  )
)
```

Grafana Explore → Tempo:

- Free-text trace search by `service.name = therapyrag-api`.
- TraceQL: `{ name = "POST /api/v1/chat" && duration > 5s }`.

## PHI posture

- Request / response bodies are **never** attached to spans. FastAPI
  auto-instrumentation records route, status code, and duration — not
  payloads.
- The collector additionally drops `http.request.body`,
  `http.response.body`, and `db.statement` attributes as a belt-and-
  braces defence (see the `attributes/phi_scrub` processor).
- Patient and therapist IDs stay in logs (which are PHI-scoped already)
  rather than spans, so trace export doesn't need to go through the
  same redaction pipeline.

## Troubleshooting

**No data in Grafana.** Check `OTEL_ENABLED=true`, restart the API. In
the API logs look for `OpenTelemetry initialized (…)`. Then check the
collector: `docker logs therapyrag-otel-collector`. If it's silent,
the API isn't reaching it — confirm `OTEL_EXPORTER_OTLP_ENDPOINT`
points at `http://localhost:4317` from the host and `http://otel-
collector:4317` from other containers.

**Collector refuses connections.** Port 4317 is already in use. Stop
any previous OTEL collector you may have running.

**Grafana won't start.** Port 3001 clash. Edit the `grafana` service
in `docker-compose.observability.yml` and remap.

**Dashboard is empty for a specific panel.** The metric name may not
be emitted yet — `worker.transcription` only appears after a
transcription job runs. Trigger one via the usual session upload
flow.

**Telemetry breaking a test.** It shouldn't — `init_telemetry` is a
no-op when the env var is unset. If you see spurious failures, check
for a stray `OTEL_ENABLED=true` in your shell and unset it.
