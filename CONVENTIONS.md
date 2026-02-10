# Conventions

## Code Style

### Python
- Python 3.12+
- Type hints required on all functions
- mypy strict mode enabled
- Ruff for linting and formatting

### Naming
| Element | Convention | Example |
|---------|------------|---------|
| Files | snake_case | `session_service.py` |
| Classes | PascalCase | `SessionService` |
| Functions | snake_case | `get_session_by_id` |
| Constants | SCREAMING_SNAKE | `MAX_UPLOAD_SIZE` |
| Private | Leading underscore | `_internal_helper` |

### Imports
```python
# Standard library
from datetime import datetime
from typing import Optional

# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local - absolute imports only
from src.core.config import settings
from src.services.session_service import SessionService
```

## Async Patterns

### Always async for I/O
```python
# YES
async def get_session(session_id: UUID) -> Session:
    async with get_session() as db:
        return await db.get(Session, session_id)

# NO - blocks event loop
def get_session(session_id: UUID) -> Session:
    with get_session() as db:
        return db.get(Session, session_id)
```

### Use httpx for HTTP calls
```python
async with httpx.AsyncClient() as client:
    response = await client.post(url, json=data)
```

## Repository Pattern

### Services call repositories, never ORM directly
```python
# YES - in service
class SessionService:
    def __init__(self, repo: SessionRepository):
        self.repo = repo

    async def get_session(self, id: UUID) -> SessionDTO:
        db_session = await self.repo.get_by_id(id)
        return SessionDTO.model_validate(db_session)

# NO - ORM in service
class SessionService:
    async def get_session(self, id: UUID, db: AsyncSession):
        return await db.get(Session, id)  # Leaky abstraction
```

## Domain/DB Separation

### Pydantic DTOs for API, SQLAlchemy for persistence
```python
# src/models/domain/session.py (API contract)
class SessionDTO(BaseModel):
    id: UUID
    status: str
    created_at: datetime

# src/models/db/session.py (ORM)
class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    status: Mapped[str]
    created_at: Mapped[datetime]
```

## Error Handling

### Use custom exceptions
```python
# src/core/exceptions.py
class SessionNotFoundError(AppError):
    status_code = 404
    message = "Session not found"

# In service
if not session:
    raise SessionNotFoundError(session_id=session_id)
```

### Never expose internal errors to API
```python
# YES
except SQLAlchemyError as e:
    logger.exception("Database error", session_id=session_id)
    raise InternalServerError()

# NO
except SQLAlchemyError as e:
    raise HTTPException(500, str(e))  # Leaks internals
```

## Logging

### Use structlog, never print()
```python
import structlog
logger = structlog.get_logger()

# YES
logger.info("session_created", session_id=session.id, patient_id=patient_id)

# NO
print(f"Created session {session.id}")
```

### Exclude PHI from logs
```python
# In structlog config
structlog.configure(
    processors=[
        structlog.processors.ExcludeKeys(["patient_name", "transcript"])
    ]
)
```

## Testing

### Use pytest-asyncio for async tests
```python
@pytest.mark.asyncio
async def test_create_session():
    service = SessionService(mock_repo)
    result = await service.create_session(data)
    assert result.status == "pending"
```

### Mock external services
```python
@pytest.fixture
def mock_deepgram(mocker):
    return mocker.patch("src.services.transcription.deepgram_client")
```

## Git

### Commit message format
```
type: short description

Longer explanation if needed.
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

### Branch naming
```
feat/add-consent-endpoint
fix/transcription-timeout
refactor/session-service
```

## Anti-Patterns (DO NOT)

- ❌ Import from sibling packages (use absolute imports)
- ❌ Use `print()` for logging
- ❌ Expose ORM models in API responses
- ❌ Write synchronous I/O code
- ❌ Catch bare `Exception`
- ❌ Update/delete consent records (immutable audit trail)
- ❌ Store PHI in logs
- ❌ Use offset-based pagination (use cursor)
