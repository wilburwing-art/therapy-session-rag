# AGENTS.md - Build and Test Instructions

This file contains operational instructions for building, testing, and validating work in this codebase.

## Tech Stack

- Python 3.11+
- FastAPI
- PostgreSQL with pgvector
- Redis + RQ
- pytest for testing
- ruff for linting
- mypy for type checking

## Setup Commands

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Start services (requires Docker)
docker compose up -d

# Run database migrations
alembic upgrade head
```

## Validation Commands (Backpressure)

**IMPORTANT**: Run ALL validation commands before committing. Do NOT commit if any fail.

```bash
# Type checking (MUST PASS)
mypy src --strict

# Linting (MUST PASS)
ruff check src tests
ruff format --check src tests

# Unit tests (MUST PASS)
pytest tests/unit -v --tb=short

# Integration tests (run if services are up)
pytest tests/integration -v --tb=short

# All tests with coverage
pytest tests -v --cov=src --cov-report=term-missing --cov-fail-under=80
```

## Before Each Commit

1. Run `ruff format src tests` to auto-format
2. Run `ruff check src tests --fix` to auto-fix lint issues
3. Run `mypy src --strict` - fix any type errors
4. Run `pytest tests -v` - all tests must pass
5. Only then: `git add . && git commit -m "descriptive message"`

## Code Patterns

### API Endpoints
- Use dependency injection for services
- Return Pydantic models, not dicts
- Use HTTPException for errors with RFC 7807 format
- Always add OpenAPI descriptions

### Services
- One service per domain concept
- Services take repositories via constructor
- Async where I/O is involved
- Return domain models, not ORM models

### Database
- Use SQLAlchemy 2.0 style (select, not query)
- Alembic for migrations
- Repository pattern for data access
- Use transactions explicitly

### Tests
- Unit tests mock external dependencies
- Integration tests use real database (test container)
- Each test file mirrors src structure
- Fixtures in conftest.py

## File Naming

```
src/
  api/
    v1/
      endpoints/
        sessions.py      # /api/v1/sessions/*
        chat.py          # /api/v1/chat/*
      dependencies.py    # FastAPI dependencies
      router.py          # Main v1 router
  services/
    consent_service.py
    session_service.py
    transcription_service.py
    embedding_service.py
    chat_service.py
  models/
    domain/              # Pydantic models
    db/                  # SQLAlchemy models
  repositories/
    consent_repo.py
    session_repo.py
  workers/
    transcription_worker.py
    embedding_worker.py
  core/
    config.py            # Settings
    database.py          # DB setup
    exceptions.py        # Custom exceptions
tests/
  unit/
    services/
    api/
  integration/
    test_consent_flow.py
    test_transcription_flow.py
  conftest.py
```

## Common Gotchas

1. **pgvector**: Must run `CREATE EXTENSION vector;` before using
2. **Async**: FastAPI endpoints are async, use `async def`
3. **Pydantic v2**: Use `model_dump()` not `dict()`
4. **SQLAlchemy 2.0**: Use `select()` not `query()`
5. **Type hints**: Always include return types
6. **Tests**: Use `pytest.mark.asyncio` for async tests

## Progress Tracking

Update `IMPLEMENTATION_PLAN.md` after completing each task:
- Change `[ ]` to `[x]` for completed items
- Add notes about any issues encountered
- If blocked, document why and move to next task
