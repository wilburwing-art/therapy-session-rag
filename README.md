# TherapyRAG

**Session Recording -> Transcription -> Patient-Facing RAG Chatbot**

A demo-ready backend platform that enables therapy providers to record sessions (with consent), transcribe them, and power a patient-facing chatbot that can answer questions like "What homework did we discuss last week?"

> Built for pitching to existing telehealth platforms and investors.

## Features

- **HIPAA-Critical Consent Management** - Full audit trail, immutable records
- **Recording Ingestion** - Accept audio/video uploads with async processing
- **Automatic Transcription** - Deepgram integration with speaker diarization
- **Semantic Search** - pgvector embeddings for relevant context retrieval
- **RAG Chatbot** - Claude-powered responses with session citations
- **API Key Authentication** - Simple auth for platform integration
- **Row-Level Security** - Multi-tenant isolation via TenantContext
- **Cursor-Based Pagination** - Efficient pagination for large datasets
- **Rate Limiting** - Redis-backed rate limiting per patient

## Architecture

```
+------------------+     +-------------------+     +------------------+
|  Recording UI    |---->|  Transcription    |---->|  Vector Store    |
|  + Consent       |     |  Pipeline         |     |  (pgvector)      |
+------------------+     +-------------------+     +--------+---------+
                                                           |
+------------------+     +-------------------+              |
|  Patient Chat    |<--->|  RAG Chatbot      |<------------+
|  Interface       |     |  (Claude)         |
+------------------+     +-------------------+
```

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### 1. Clone and Setup

```bash
git clone <repo-url>
cd therapy-session-rag

# Install dependencies with uv (recommended)
uv sync

# Or with pip
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env
# Edit .env with your API keys (Deepgram, OpenAI, Anthropic)
```

### 2. Start Services

```bash
# Start PostgreSQL (with pgvector), Redis, MinIO
docker compose up -d postgres redis minio minio-setup

# Wait for services to be healthy
docker compose ps
```

### 3. Run Migrations

```bash
uv run alembic upgrade head
```

### 4. Start the API

```bash
# Development mode with auto-reload
uv run uvicorn src.main:app --reload

# Or run via Docker
docker compose up api
```

Visit http://localhost:8000/docs for the interactive API documentation.

### 5. Start Background Workers (for transcription/embedding)

```bash
# In separate terminals:
uv run python -m rq.cli worker transcription --url redis://localhost:6379
uv run python -m rq.cli worker embedding --url redis://localhost:6379

# Or via Docker
docker compose up worker-transcription worker-embedding
```

## Development

### Validation Commands

```bash
# Run full e2e test suite (recommended)
./scripts/e2e_test.sh

# Individual commands:
uv run ruff check src/ tests/           # Lint
uv run mypy src/                         # Type check
uv run pytest tests/unit -v              # Unit tests
uv run pytest tests/integration -v       # Integration tests (requires docker)
```

### Test Status

- **Unit tests**: 407 passing
- **Lint**: Clean (ruff)
- **Type check**: Clean (mypy strict mode)

## API Overview

### Authentication
All endpoints (except `/health*`) require an API key in the `X-API-Key` header.

### Health Endpoints

```
GET  /health           # Simple liveness check
GET  /health/live      # Kubernetes liveness probe
GET  /health/ready     # Kubernetes readiness probe (checks DB, Redis)
GET  /health/detailed  # Full component status
```

### Consent Endpoints

```
POST   /api/v1/consent                    # Grant recording consent
DELETE /api/v1/consent                    # Revoke consent
GET    /api/v1/consent/{patient_id}/check # Check consent status
GET    /api/v1/consent/{patient_id}/active # Get all active consents
GET    /api/v1/consent/{patient_id}/audit  # Get consent audit log
```

### Session Endpoints

```
POST   /api/v1/sessions                       # Create session
GET    /api/v1/sessions/{id}                  # Get session details
PATCH  /api/v1/sessions/{id}                  # Update session
GET    /api/v1/sessions                       # List sessions (cursor pagination)
POST   /api/v1/sessions/{id}/recording        # Upload recording
POST   /api/v1/sessions/{id}/transcribe       # Start transcription
GET    /api/v1/sessions/{id}/transcript       # Get transcript
GET    /api/v1/sessions/{id}/transcription-status # Check transcription status
```

### Chat Endpoints

```
POST   /api/v1/chat?patient_id=uuid     # Send message to RAG chatbot
GET    /api/v1/chat/sessions-count      # Get indexed session count
GET    /api/v1/chat/chunks-count        # Get indexed chunk count
GET    /api/v1/chat/rate-limit          # Check rate limit status
```

### Example: List Sessions with Cursor Pagination

```bash
# First page
curl "http://localhost:8000/api/v1/sessions?limit=10" \
  -H "X-API-Key: your_key"

# Response includes next_cursor for pagination
{
  "items": [...],
  "next_cursor": "eyJzb3J0X3ZhbHVlIjoiMjAyNC...",
  "has_more": true
}

# Next page
curl "http://localhost:8000/api/v1/sessions?limit=10&cursor=eyJzb3J0X3ZhbHVlIjoiMjAyNC..." \
  -H "X-API-Key: your_key"
```

### Example: Chat Request

```bash
curl -X POST "http://localhost:8000/api/v1/chat?patient_id=<uuid>" \
  -H "X-API-Key: your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What did we discuss about managing anxiety?",
    "top_k": 5
  }'
```

Response:
```json
{
  "response": "In your session, you discussed several techniques for managing anxiety including breathing exercises and cognitive reframing...",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "sources": [
    {
      "session_id": "550e8400-e29b-41d4-a716-446655440001",
      "chunk_id": "550e8400-e29b-41d4-a716-446655440002",
      "content_preview": "Patient discussed feeling anxious about...",
      "relevance_score": 0.89,
      "start_time": 120.5,
      "speaker": "Speaker 0"
    }
  ]
}
```

### Rate Limiting

The chat endpoint is rate-limited to 20 messages per hour per patient. When exceeded, you'll receive a 429 response with `retry_after` indicating seconds until reset.

## Tech Stack

- **Python 3.12+** / FastAPI
- **PostgreSQL 16** with pgvector extension
- **Redis 7** + RQ for job queues and rate limiting
- **MinIO** for S3-compatible object storage
- **Deepgram** for transcription with speaker diarization
- **OpenAI** for text embeddings (text-embedding-3-small)
- **Claude** (claude-sonnet-4) for RAG chat responses

## Project Structure

```
src/
├── api/v1/          # FastAPI endpoints
│   └── endpoints/   # Consent, Sessions, Chat
├── core/            # Config, database, exceptions, logging, health
│   ├── pagination.py    # Cursor-based pagination utilities
│   └── tenant.py        # Row-level security (TenantContext)
├── models/
│   ├── db/          # SQLAlchemy models
│   └── domain/      # Pydantic schemas
├── repositories/    # Database access layer
├── services/        # Business logic
│   ├── chat_service.py
│   ├── claude_client.py
│   ├── deepgram_client.py
│   ├── embedding_client.py
│   ├── embedding_service.py
│   ├── rate_limiter.py
│   └── ...
└── workers/         # RQ background workers

tests/
├── unit/            # 407 unit tests
└── integration/     # Full pipeline tests
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | required |
| `REDIS_URL` | Redis connection string | required |
| `MINIO_ENDPOINT` | MinIO server endpoint | required |
| `MINIO_ACCESS_KEY` | MinIO access key | required |
| `MINIO_SECRET_KEY` | MinIO secret key | required |
| `DEEPGRAM_API_KEY` | Deepgram API key | required |
| `OPENAI_API_KEY` | OpenAI API key | required |
| `ANTHROPIC_API_KEY` | Anthropic API key | required |
| `APP_ENV` | Environment (development/staging/production/test) | development |
| `APP_LOG_LEVEL` | Log level (DEBUG/INFO/WARNING/ERROR) | INFO |
| `CHAT_RATE_LIMIT_PER_HOUR` | Chat messages per hour per patient | 20 |

## Security Features

### Row-Level Security (Multi-Tenant Isolation)

All session queries are scoped to the authenticated organization via `TenantContext`:

```python
# Automatically validates user belongs to tenant's organization
tenant = TenantContext(organization_id=auth.organization_id, db_session=session)
await tenant.validate_session_access(session_id)
```

### Database Indexes

Composite indexes optimize common query patterns:
- `ix_sessions_patient_status` - Patient + status queries
- `ix_sessions_therapist_status` - Therapist + status queries
- `ix_sessions_patient_date` - Patient + date range queries
- `ix_consents_patient_therapist_type_granted` - Consent lookups

## License

MIT
