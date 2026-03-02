# TherapyRAG

[![CI](https://github.com/wilburwing-art/therapy-session-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/wilburwing-art/therapy-session-rag/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Session Recording → Transcription → Patient-Facing RAG Chatbot**

Therapy providers want to give patients access to their session content between appointments — but manual transcription is a nonstarter, and generic chatbots have no patient context. TherapyRAG closes that gap: therapists upload recordings (with consent), the pipeline auto-transcribes and indexes them, and patients get a chatbot that answers questions like *"What homework did we discuss last week?"* with cited, relevant excerpts from their own sessions.

Built as a production-ready backend targeting telehealth platform integration.

## Architecture

```
                           INGESTION PIPELINE
  ┌───────────┐    ┌───────────┐    ┌──────────────┐    ┌──────────────┐
  │  Upload   │───>│   MinIO   │───>│   Deepgram   │───>│   OpenAI     │
  │  Audio    │    │   (S3)    │    │   ASR +      │    │   Embeddings │
  │           │    │           │    │   Diarize    │    │   (1536-dim) │
  └───────────┘    └───────────┘    └──────────────┘    └──────┬───────┘
       │                                                       │
       │  consent check                              chunk + store
       v                                                       v
  ┌───────────┐                                    ┌───────────────────┐
  │  Consent  │                                    │   PostgreSQL      │
  │  Audit    │                                    │   + pgvector      │
  │  (append- │                                    │                   │
  │   only)   │                                    │  sessions         │
  └───────────┘                                    │  transcripts      │
                                                   │  chunks + vectors │
                                                   └─────────┬─────────┘
                           QUERY PATH                        │
  ┌───────────┐    ┌──────────────────────────┐              │
  │  Patient  │<──>│  Claude RAG Chat         │<─── semantic search
  │  Chat UI  │    │  + citations             │    (cosine similarity,
  └───────────┘    │  + safety guardrails     │     patient-scoped)
                   └──────────────────────────┘
                              │
                   ┌──────────┴──────────┐
                   │  Redis              │
                   │  rate limits + jobs  │
                   └─────────────────────┘
```

### Component Breakdown

| Layer | Tech | Role |
|-------|------|------|
| **API** | FastAPI (async) | 30+ endpoints across consent, sessions, chat, admin |
| **Database** | PostgreSQL 16 + pgvector | Relational data + vector similarity search |
| **Queue** | Redis 7 + RQ | Async transcription and embedding jobs |
| **Storage** | MinIO (S3-compatible) | Audio/video recording files |
| **Transcription** | Deepgram | Speech-to-text with speaker diarization |
| **Embeddings** | OpenAI (text-embedding-3-small) | 1536-dimensional chunk vectors |
| **Chat LLM** | Claude (claude-sonnet-4) | RAG responses with session citations |
| **Safety** | Custom guardrails | Crisis detection, input/output filtering |

### Data Isolation Model

Every query is scoped to the authenticated organization via `TenantContext`. Patient A never sees Patient B's data — enforced at the repository layer, not just the API layer.

```
API Key (X-API-Key) → Organization → TenantContext
  └── All queries filtered: WHERE patient_id IN (SELECT id FROM users WHERE org_id = ?)
```

Consent is append-only: grants and revocations create new immutable records. No UPDATE, no DELETE. Full audit trail with IP, user-agent, and timestamps.

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- API keys: [Deepgram](https://deepgram.com), [OpenAI](https://platform.openai.com), [Anthropic](https://console.anthropic.com)

### Setup

```bash
git clone https://github.com/wilburwing-art/therapy-session-rag.git
cd therapy-session-rag

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Add your API keys to .env

# Start infrastructure
docker compose up -d postgres redis minio minio-setup

# Run migrations
uv run alembic upgrade head

# Start API server
uv run uvicorn src.main:app --reload

# Start background workers (separate terminals)
uv run python -m rq.cli worker transcription --url redis://localhost:6379
uv run python -m rq.cli worker embedding --url redis://localhost:6379
```

Or run the full stack via Docker:
```bash
docker compose up
```

API docs at http://localhost:8000/docs

## API

All endpoints (except `/health*`) require `X-API-Key` header.

### Consent

```
POST   /api/v1/consent                      # Grant recording consent
DELETE /api/v1/consent                      # Revoke consent (creates revocation record)
GET    /api/v1/consent/{patient_id}/check   # Check active consent
GET    /api/v1/consent/{patient_id}/audit   # Full immutable audit trail
```

### Sessions

```
POST   /api/v1/sessions                       # Create session
POST   /api/v1/sessions/{id}/recording        # Upload audio/video
POST   /api/v1/sessions/{id}/transcribe       # Queue transcription job
GET    /api/v1/sessions/{id}/transcript       # Get transcript
GET    /api/v1/sessions                       # List (cursor pagination)
```

### Chat

```
POST   /api/v1/chat?patient_id=uuid     # Send message → RAG response with citations
GET    /api/v1/chat/rate-limit           # Check remaining quota (20/hr per patient)
GET    /api/v1/chat/conversations        # List conversation threads
```

### Example: Chat Request

```bash
curl -X POST "http://localhost:8000/api/v1/chat?patient_id=<uuid>" \
  -H "X-API-Key: your_key" \
  -H "Content-Type: application/json" \
  -d '{"message": "What did we discuss about managing anxiety?", "top_k": 5}'
```

```json
{
  "response": "In your session, you discussed several techniques for managing anxiety...",
  "conversation_id": "550e8400-...",
  "sources": [
    {
      "session_id": "...",
      "chunk_id": "...",
      "content_preview": "Patient discussed feeling anxious about...",
      "relevance_score": 0.89,
      "start_time": 120.5,
      "speaker": "Speaker 0"
    }
  ]
}
```

## Project Structure

```
src/
├── api/v1/endpoints/     # Consent, Sessions, Chat, Users, Organizations
├── core/                 # Config, database, security, tenant isolation, pagination
├── models/
│   ├── db/               # SQLAlchemy ORM (12 models)
│   └── domain/           # Pydantic DTOs (API contracts)
├── repositories/         # Data access layer (10 repos, including vector search)
├── services/             # Business logic (21 service modules)
│   ├── chat_service.py       # RAG orchestration: embed → search → Claude
│   ├── deepgram_client.py    # ASR with speaker diarization
│   ├── embedding_service.py  # Chunking + OpenAI embeddings
│   ├── claude_client.py      # LLM integration
│   ├── safety/               # Guardrails, risk detection, audit
│   └── ...
├── workers/              # RQ background job processors
└── evaluation/           # RAG quality metrics

tests/
├── unit/                 # 407 tests (all passing)
└── integration/          # Full pipeline tests
```

## Validation

```bash
uv run ruff check src/ tests/    # Lint
uv run mypy src/                 # Type check (strict mode)
uv run pytest tests/unit -v      # 407 unit tests
./scripts/e2e_test.sh            # Full E2E flow
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL async connection string |
| `REDIS_URL` | Redis for job queue + rate limiting |
| `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | S3-compatible storage |
| `DEEPGRAM_API_KEY` | Transcription service |
| `OPENAI_API_KEY` | Embedding generation |
| `ANTHROPIC_API_KEY` | Claude chat responses |
| `CHAT_RATE_LIMIT_PER_HOUR` | Per-patient chat limit (default: 20) |
| `SAFETY_ENABLED` | Clinical AI guardrails (default: true) |

## Tech Stack

Python 3.12+ / FastAPI / PostgreSQL 16 + pgvector / Redis 7 + RQ / MinIO / Deepgram / OpenAI Embeddings / Claude / SQLAlchemy 2.0 (async) / Alembic / mypy (strict) / ruff / structlog

## License

MIT
