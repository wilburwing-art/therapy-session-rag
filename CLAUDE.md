# Therapy Session RAG - Project Instructions

## Project Overview

A RAG-powered backend for therapy/telehealth platforms that enables:
- Recording therapy sessions with consent management
- Automatic transcription via Deepgram
- Semantic search via pgvector embeddings
- Patient-facing AI chatbot powered by Claude

## Tech Stack

- **Framework**: FastAPI (async)
- **Database**: PostgreSQL 16 + pgvector
- **Queue**: Redis + RQ
- **Storage**: MinIO (S3-compatible)
- **AI**: Deepgram (transcription), OpenAI (embeddings), Claude (chat)

## Common Commands

```bash
# Start services
docker compose up -d postgres redis minio

# Run API server
uv run uvicorn src.main:app --reload

# Run workers (separate terminals)
uv run python -m rq.cli worker transcription --url redis://localhost:6379
uv run python -m rq.cli worker embedding --url redis://localhost:6379

# Run tests
uv run pytest tests/ -v

# Lint and type check
uv run ruff check src/ tests/
uv run mypy src/

# Run full e2e test suite
./scripts/e2e_test.sh
```

## Current Status

- **Unit Tests**: 407 passing
- **Lint**: Clean (ruff)
- **Type Check**: Clean (mypy strict mode)

---

## Completion Criteria

The task is **COMPLETE** when ALL of the following pass:

1. `./scripts/e2e_test.sh` exits with code 0
2. `uv run ruff check src/ tests/` passes (no lint errors)
3. `uv run mypy src/` passes (no type errors)
4. `uv run pytest tests/ -v` passes (all tests green)

### How to Run

```bash
# Standard validation:
./scripts/e2e_test.sh

# If it fails, fix the issue and re-run until all checks pass
```

---

## Key Files

| File | Purpose |
|------|---------|
| `src/core/tenant.py` | Row-level security (TenantContext) |
| `src/core/pagination.py` | Cursor-based pagination utilities |
| `src/services/session_service.py` | Session management with tenant validation |
| `src/services/transcription_service.py` | Transcription pipeline (queues embedding) |
| `src/services/chat_service.py` | RAG chatbot service |
| `scripts/e2e_test.sh` | Full validation script |

---

## Security Notes

- Never commit real API keys
- All patient data queries must filter by organization/patient ID
- Use TenantContext for row-level security in all session operations
