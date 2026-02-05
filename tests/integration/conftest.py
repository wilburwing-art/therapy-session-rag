"""Integration test fixtures and configuration."""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Test environment setup - must be before src imports
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/therapy_test",
)
os.environ["REDIS_URL"] = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")
os.environ["MINIO_ENDPOINT"] = "localhost:9000"
os.environ["MINIO_ACCESS_KEY"] = "minioadmin"
os.environ["MINIO_SECRET_KEY"] = "minioadmin"
os.environ["MINIO_BUCKET"] = "therapy-test"
os.environ["DEEPGRAM_API_KEY"] = "test_deepgram_key"
os.environ["OPENAI_API_KEY"] = "test_openai_key"
os.environ["ANTHROPIC_API_KEY"] = "test_anthropic_key"

from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.security import hash_api_key
from src.main import app
from src.models.db.api_key import ApiKey
from src.models.db.base import Base
from src.models.db.consent import Consent, ConsentStatus, ConsentType
from src.models.db.organization import Organization
from src.models.db.user import User, UserRole

# Path to test audio file
TEST_AUDIO_PATH = "/Users/wilburpyn/Downloads/Wilbur-therapy-1-15-26.m4a"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create test database engine."""
    settings = get_settings()
    engine = create_async_engine(
        str(settings.database_url),
        echo=False,
        pool_pre_ping=True,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup - drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with transaction rollback."""
    async_session_factory = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()


@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession) -> Organization:
    """Create a test organization."""
    org = Organization(
        id=uuid.uuid4(),
        name="Test Therapy Clinic",
    )
    db_session.add(org)
    await db_session.flush()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def test_therapist(db_session: AsyncSession, test_org: Organization) -> User:
    """Create a test therapist user."""
    user = User(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        email="therapist@test.com",
        role=UserRole.THERAPIST,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_patient(db_session: AsyncSession, test_org: Organization) -> User:
    """Create a test patient user."""
    user = User(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        email="patient@test.com",
        role=UserRole.PATIENT,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_api_key(db_session: AsyncSession, test_org: Organization) -> tuple[str, ApiKey]:
    """Create a test API key and return both plaintext and model."""
    plaintext_key = f"tsr_test_{uuid.uuid4().hex}"
    key_hash = hash_api_key(plaintext_key)

    api_key = ApiKey(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        key_hash=key_hash,
        name="Test API Key",
        is_active=True,
    )
    db_session.add(api_key)
    await db_session.flush()
    await db_session.refresh(api_key)
    return plaintext_key, api_key


@pytest_asyncio.fixture
async def test_consent(
    db_session: AsyncSession,
    test_patient: User,
    test_therapist: User,
) -> Consent:
    """Create test consent records for all types."""
    consents = []
    for consent_type in ConsentType:
        consent = Consent(
            id=uuid.uuid4(),
            patient_id=test_patient.id,
            therapist_id=test_therapist.id,
            consent_type=consent_type,
            status=ConsentStatus.GRANTED,
            granted_at=datetime.now(UTC),
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
        db_session.add(consent)
        consents.append(consent)

    await db_session.flush()
    for consent in consents:
        await db_session.refresh(consent)

    # Return the recording consent
    return next(c for c in consents if c.consent_type == ConsentType.RECORDING)


@pytest_asyncio.fixture
async def async_client(
    db_session: AsyncSession,
    test_api_key: tuple[str, ApiKey],
) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for API testing."""
    plaintext_key, _ = test_api_key

    # Override the database session dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": plaintext_key},
    ) as client:
        yield client

    app.dependency_overrides.clear()


# Mock fixtures for external services


@pytest.fixture
def mock_deepgram_response() -> dict[str, Any]:
    """Mock Deepgram transcription response."""
    return {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Hello, how are you feeling today? I've been feeling anxious lately.",
                            "confidence": 0.95,
                            "words": [
                                {"word": "Hello", "start": 0.0, "end": 0.5, "confidence": 0.99, "speaker": 0},
                                {"word": "how", "start": 0.6, "end": 0.8, "confidence": 0.98, "speaker": 0},
                                {"word": "are", "start": 0.9, "end": 1.0, "confidence": 0.97, "speaker": 0},
                                {"word": "you", "start": 1.1, "end": 1.3, "confidence": 0.99, "speaker": 0},
                                {"word": "feeling", "start": 1.4, "end": 1.8, "confidence": 0.96, "speaker": 0},
                                {"word": "today", "start": 1.9, "end": 2.3, "confidence": 0.98, "speaker": 0},
                                {"word": "I've", "start": 3.0, "end": 3.2, "confidence": 0.95, "speaker": 1},
                                {"word": "been", "start": 3.3, "end": 3.5, "confidence": 0.97, "speaker": 1},
                                {"word": "feeling", "start": 3.6, "end": 4.0, "confidence": 0.98, "speaker": 1},
                                {"word": "anxious", "start": 4.1, "end": 4.6, "confidence": 0.94, "speaker": 1},
                                {"word": "lately", "start": 4.7, "end": 5.1, "confidence": 0.96, "speaker": 1},
                            ],
                        }
                    ]
                }
            ],
            "utterances": [
                {
                    "transcript": "Hello, how are you feeling today?",
                    "start": 0.0,
                    "end": 2.3,
                    "speaker": 0,
                    "confidence": 0.97,
                    "words": [],
                },
                {
                    "transcript": "I've been feeling anxious lately.",
                    "start": 3.0,
                    "end": 5.1,
                    "speaker": 1,
                    "confidence": 0.96,
                    "words": [],
                },
            ],
        },
        "metadata": {
            "duration": 5.1,
            "language": "en",
        },
    }


@pytest.fixture
def mock_embedding() -> list[float]:
    """Mock embedding vector (1536 dimensions for text-embedding-3-small)."""
    import random
    random.seed(42)  # Reproducible
    return [random.uniform(-1, 1) for _ in range(1536)]


@pytest.fixture
def mock_claude_response() -> str:
    """Mock Claude chat response."""
    return (
        "Based on what you shared in your recent session, it sounds like you've been "
        "experiencing some anxiety. Your therapist asked about how you're feeling, and "
        "you mentioned feeling anxious lately. This is a common experience, and it's "
        "good that you're able to identify and express these feelings. Remember, it's "
        "always helpful to discuss these concerns further with your therapist."
    )


@pytest.fixture
def mock_deepgram_client(mock_deepgram_response):
    """Mock the Deepgram client."""
    with patch("src.services.transcription_service.DeepgramClient") as mock:
        client_instance = MagicMock()
        client_instance.transcribe_file = AsyncMock()

        # Parse the mock response into a TranscriptionResult
        from src.services.deepgram_client import Segment, TranscriptionResult

        result = TranscriptionResult(
            full_text="Hello, how are you feeling today? I've been feeling anxious lately.",
            segments=[
                Segment(
                    text="Hello, how are you feeling today?",
                    start_time=0.0,
                    end_time=2.3,
                    speaker="Speaker 0",
                    confidence=0.97,
                    words=[],
                ),
                Segment(
                    text="I've been feeling anxious lately.",
                    start_time=3.0,
                    end_time=5.1,
                    speaker="Speaker 1",
                    confidence=0.96,
                    words=[],
                ),
            ],
            duration_seconds=5.1,
            language="en",
            confidence=0.95,
            word_count=11,
        )
        client_instance.transcribe_file.return_value = result
        mock.return_value = client_instance
        yield mock


@pytest.fixture
def mock_embedding_client(mock_embedding):
    """Mock the OpenAI embedding client."""
    with patch("src.services.embedding_service.EmbeddingClient") as mock:
        client_instance = MagicMock()
        client_instance.embed_text = AsyncMock()
        client_instance.embed_batch = AsyncMock()

        from src.services.embedding_client import EmbeddingResult

        def make_result(text: str) -> EmbeddingResult:
            return EmbeddingResult(
                text=text,
                embedding=mock_embedding,
                model="text-embedding-3-small",
                token_count=len(text) // 4,
            )

        client_instance.embed_text.side_effect = lambda t: make_result(t)
        client_instance.embed_batch.side_effect = lambda texts: [make_result(t) for t in texts]

        mock.return_value = client_instance
        yield mock


@pytest.fixture
def mock_claude_client(mock_claude_response):
    """Mock the Claude client."""
    with patch("src.services.chat_service.ClaudeClient") as mock:
        client_instance = MagicMock()
        client_instance.chat = AsyncMock()

        from src.services.claude_client import ChatResponse

        client_instance.chat.return_value = ChatResponse(
            content=mock_claude_response,
            model="claude-sonnet-4-20250514",
            input_tokens=500,
            output_tokens=150,
            stop_reason="end_turn",
        )
        client_instance.create_rag_system_prompt = MagicMock(
            return_value="You are a supportive AI assistant..."
        )

        mock.return_value = client_instance
        yield mock


@pytest.fixture
def mock_storage_service():
    """Mock the MinIO storage service."""
    with patch("src.services.storage_service.StorageService") as mock:
        service_instance = MagicMock()
        service_instance.upload_file = AsyncMock(return_value=None)
        service_instance.download_file = AsyncMock(return_value=b"fake audio data")
        service_instance.get_presigned_url = AsyncMock(
            return_value="http://localhost:9000/therapy-test/fake-key"
        )
        service_instance.generate_key = MagicMock(
            side_effect=lambda filename, prefix="": f"{prefix}/{uuid.uuid4()}/{filename}"
        )
        service_instance.file_exists = AsyncMock(return_value=True)

        mock.return_value = service_instance
        yield mock


@pytest.fixture
def mock_redis():
    """Mock Redis for rate limiting."""
    with patch("src.services.rate_limiter.Redis") as mock:
        redis_instance = MagicMock()
        redis_instance.get.return_value = None
        redis_instance.ttl.return_value = 3600
        redis_instance.pipeline.return_value = MagicMock(
            execute=MagicMock(return_value=[1, True, 3600])
        )
        mock.from_url.return_value = redis_instance
        yield mock


# Test data fixture
@pytest.fixture
def test_audio_path() -> str:
    """Path to the real test audio file."""
    return TEST_AUDIO_PATH


@pytest.fixture
def test_audio_content(test_audio_path: str) -> bytes | None:
    """Load test audio file if it exists."""
    if os.path.exists(test_audio_path):
        with open(test_audio_path, "rb") as f:
            return f.read()
    return None
