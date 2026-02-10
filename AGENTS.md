# TherapyRAG

Session Recording → Transcription → Patient-Facing RAG Chatbot

A HIPAA-aware backend for therapy providers: record sessions with consent, auto-transcribe via Deepgram, and power a Claude-based RAG chatbot for patients.

## Build & Test

```bash
# Install dependencies
uv sync

# Start infrastructure (Postgres+pgvector, Redis, MinIO)
docker compose up -d postgres redis minio minio-setup

# Run migrations
uv run alembic upgrade head

# Start dev server
uv run uvicorn src.main:app --reload

# Run tests
uv run pytest tests/unit -v              # Unit tests
uv run pytest tests/integration -v       # Integration tests
./scripts/e2e_test.sh                    # Full E2E flow

# Lint & type check
uv run ruff check src/ tests/
uv run ruff check src/ tests/ --fix      # Auto-fix
uv run mypy src/                         # Strict mode enabled
```

## Architecture

```
src/
├── api/v1/endpoints/     # FastAPI route handlers
├── services/             # Business logic layer
├── repositories/         # Data access layer (SQLAlchemy async)
├── models/
│   ├── domain/           # Pydantic DTOs (API contracts)
│   └── db/               # SQLAlchemy ORM models
├── core/                 # Config, database, logging, security
├── workers/              # RQ background job processors
└── evaluation/           # RAG evaluation utilities
```

### Key Patterns

- **Async-first**: All DB ops use `asyncpg`, all HTTP uses `httpx`
- **Repository pattern**: Services → Repositories → ORM models
- **Domain separation**: Pydantic DTOs never leak ORM models to API
- **TenantContext**: Row-level security via context var for multi-tenancy
- **Cursor pagination**: Use `cursor` param, not offset-based

## Code Style

- Python 3.12+
- Type hints required (mypy strict)
- Ruff for linting and formatting
- Async functions for all I/O operations
- Use `structlog` for logging, not `print()` or stdlib `logging`

## Security (HIPAA)

- **Consent audit trail is immutable** — never update/delete consent records
- **PHI in logs** — use structlog's `exclude_keys` for patient data
- **API keys** — validated via `X-API-Key` header, scoped per-platform
- **Rate limiting** — Redis-backed, per-patient limits on chat endpoint

## Database

- PostgreSQL 15+ with pgvector extension
- Alembic for migrations: `uv run alembic revision --autogenerate -m "message"`
- Connection: async via `asyncpg`, pool managed by SQLAlchemy

## Infrastructure

- **MinIO**: S3-compatible storage for recordings (local dev)
- **Redis**: Rate limiting + RQ job queue
- **RQ Workers**: Background transcription processing

## Git Workflow

- Branch from `main`
- PR titles: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
- Squash merge to main

## Known Limitations

- Phases 4-7 (transcription pipeline, embeddings, RAG chat) are partially implemented
- Deepgram integration requires API key in `.env`
- E2E tests require all services running
