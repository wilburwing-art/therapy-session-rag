# AGENTS.md - Build and Test Instructions

This file contains operational instructions for building, testing, and validating work in this codebase.

## Tech Stack

- Python 3.12+
- FastAPI (async)
- PostgreSQL 16 with pgvector
- Redis 7 + RQ
- pytest for testing
- ruff for linting
- mypy for type checking (strict mode)
- uv for dependency management

## Setup Commands

```bash
# Install dependencies with uv (recommended)
uv sync

# Or with pip
pip install -e ".[dev]"

# Start services (requires Docker)
docker compose up -d postgres redis minio

# Run database migrations
uv run alembic upgrade head
```

## Validation Commands (Backpressure)

**IMPORTANT**: Run ALL validation commands before committing. Do NOT commit if any fail.

```bash
# Full e2e test suite (RECOMMENDED - runs all checks)
./scripts/e2e_test.sh

# Individual commands:

# Type checking (MUST PASS)
uv run mypy src/

# Linting (MUST PASS)
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Unit tests (MUST PASS)
uv run pytest tests/unit -v --tb=short

# Integration tests (requires docker services)
uv run pytest tests/integration -v --tb=short

# All tests with coverage
uv run pytest tests -v --cov=src --cov-report=term-missing --cov-fail-under=80
```

## Current Status

- **Unit Tests**: 407 passing
- **Lint**: Clean
- **Type Check**: Clean (mypy strict mode)
- **Integration Tests**: Ready (requires docker)

## Before Each Commit

1. Run `./scripts/e2e_test.sh` - all checks must pass
2. If needed, run `uv run ruff format src/ tests/` to auto-format
3. If needed, run `uv run ruff check src/ tests/ --fix` to auto-fix lint issues
4. Only then: `git add . && git commit -m "descriptive message"`

## Code Patterns

### API Endpoints
- Use dependency injection for services
- Return Pydantic models, not dicts
- Use HTTPException for errors with RFC 7807 format
- Always add OpenAPI descriptions
- Use TenantContext for row-level security

### Services
- One service per domain concept
- Services take repositories via constructor
- Async where I/O is involved
- Return domain models, not ORM models
- Accept TenantContext for multi-tenant isolation

### Database
- Use SQLAlchemy 2.0 style (select, not query)
- Alembic for migrations
- Repository pattern for data access
- Use transactions explicitly
- Add composite indexes for common query patterns

### Pagination
- Use cursor-based pagination (not offset)
- Use `CursorPage[T]` from `src/core/pagination.py`
- Encode cursor with `encode_cursor()`, decode with `decode_cursor()`

### Tests
- Unit tests mock external dependencies
- Integration tests use real database (test container)
- Each test file mirrors src structure
- Fixtures in conftest.py
- Use `pytest.mark.asyncio` for async tests

## File Structure

```
src/
  api/
    v1/
      endpoints/
        sessions.py      # /api/v1/sessions/*
        chat.py          # /api/v1/chat/*
        consent.py       # /api/v1/consent/*
      dependencies.py    # FastAPI dependencies
      router.py          # Main v1 router
  core/
    config.py            # Settings
    database.py          # DB setup
    exceptions.py        # Custom exceptions
    health.py            # Health checks
    logging.py           # Structured logging
    pagination.py        # Cursor-based pagination
    tenant.py            # Row-level security
  services/
    consent_service.py
    session_service.py
    transcription_service.py
    embedding_service.py
    chat_service.py
    claude_client.py
    deepgram_client.py
    embedding_client.py
    rate_limiter.py
    storage_service.py
  models/
    domain/              # Pydantic models
    db/                  # SQLAlchemy models
  repositories/
    consent_repo.py
    session_repo.py
    chunk_repo.py
  workers/
    transcription_worker.py
    embedding_worker.py
tests/
  unit/
    api/
    services/
    core/
    models/
  integration/
    test_full_pipeline.py
  conftest.py
scripts/
  e2e_test.sh           # Full validation script
```

## Common Gotchas

1. **pgvector**: Must run `CREATE EXTENSION vector;` before using
2. **Async**: FastAPI endpoints are async, use `async def`
3. **Pydantic v2**: Use `model_dump()` not `dict()`
4. **SQLAlchemy 2.0**: Use `select()` not `query()`
5. **Type hints**: Always include return types, use Literal for constrained strings
6. **Tests**: Use `pytest.mark.asyncio` for async tests
7. **TextBlock**: When mocking Anthropic responses, use real `TextBlock` from `anthropic.types`

## Progress Tracking

Update `IMPLEMENTATION_PLAN.md` after completing each task:
- Change `[ ]` to `[x]` for completed items
- Add notes about any issues encountered
- If blocked, document why and move to next task
