"""Tests for SummarizationService."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.models.db.session_recap import SessionRecap
from src.services.claude_client import ChatResponse, ClaudeError
from src.services.summarization_service import (
    SummarizationService,
    SummarizationServiceError,
)


def _mock_claude_response(content: str, model: str = "claude-sonnet-4-test") -> ChatResponse:
    return ChatResponse(
        content=content,
        model=model,
        input_tokens=100,
        output_tokens=50,
        stop_reason="end_turn",
    )


def _mock_recap_row(session_id: uuid.UUID) -> SessionRecap:
    row = MagicMock(spec=SessionRecap)
    row.id = uuid.uuid4()
    row.session_id = session_id
    row.brief = "A short recap."
    row.key_topics = ["anxiety", "sleep"]
    row.emotional_tone = "reflective"
    row.homework_assigned = [{"task": "Journal nightly", "notes": None}]
    row.follow_ups = ["Revisit sleep hygiene"]
    row.risk_flags = []
    row.model_name = "claude-sonnet-4-test"
    row.generated_at = datetime.now(UTC)
    row.created_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    return row


@pytest.fixture
def session_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_db_session() -> MagicMock:
    db = MagicMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def service(mock_db_session: MagicMock) -> SummarizationService:
    claude = MagicMock()
    claude.chat = AsyncMock()
    svc = SummarizationService(
        db_session=mock_db_session,
        claude_client=claude,
    )
    svc.session_repo = MagicMock()
    svc.transcript_repo = MagicMock()
    svc.recap_repo = MagicMock()
    return svc


def test_parse_payload_plain_json() -> None:
    raw = '{"brief": "hi", "key_topics": ["a"], "emotional_tone": null, "homework_assigned": [], "follow_ups": [], "risk_flags": []}'
    result = SummarizationService._parse_payload(raw)
    assert result.brief == "hi"
    assert result.key_topics == ["a"]


def test_parse_payload_with_markdown_fence() -> None:
    raw = """```json
{"brief": "fenced", "key_topics": [], "emotional_tone": null, "homework_assigned": [], "follow_ups": [], "risk_flags": []}
```"""
    result = SummarizationService._parse_payload(raw)
    assert result.brief == "fenced"


def test_parse_payload_with_surrounding_prose() -> None:
    raw = 'Here is the recap: {"brief": "prose-wrapped", "key_topics": [], "emotional_tone": null, "homework_assigned": [], "follow_ups": [], "risk_flags": []} Let me know if you need anything else.'
    result = SummarizationService._parse_payload(raw)
    assert result.brief == "prose-wrapped"


def test_parse_payload_normalizes_string_homework() -> None:
    raw = '{"brief": "ok", "key_topics": [], "emotional_tone": null, "homework_assigned": ["Journal for 10 min"], "follow_ups": [], "risk_flags": []}'
    result = SummarizationService._parse_payload(raw)
    assert len(result.homework_assigned) == 1
    assert result.homework_assigned[0].task == "Journal for 10 min"
    assert result.homework_assigned[0].notes is None


def test_parse_payload_raises_on_malformed_json() -> None:
    with pytest.raises(SummarizationServiceError):
        SummarizationService._parse_payload("not json at all")


def test_parse_payload_raises_on_schema_violation() -> None:
    # Missing required 'brief' field
    raw = '{"key_topics": [], "emotional_tone": null, "homework_assigned": [], "follow_ups": [], "risk_flags": []}'
    with pytest.raises(SummarizationServiceError):
        SummarizationService._parse_payload(raw)


def test_format_transcript_renders_segments() -> None:
    rendered = SummarizationService._format_transcript_for_prompt(
        full_text="fallback",
        segments=[
            {"text": "Hello.", "speaker": "Speaker 0", "start_time": 0.0},
            {"text": "Hi.", "speaker": "Speaker 1", "start_time": 1.5},
        ],
    )
    assert "[0.0s] Speaker 0: Hello." in rendered
    assert "[1.5s] Speaker 1: Hi." in rendered
    assert "fallback" not in rendered


def test_format_transcript_falls_back_to_full_text() -> None:
    rendered = SummarizationService._format_transcript_for_prompt(
        full_text="raw text only",
        segments=[],
    )
    assert rendered == "raw text only"


def test_format_transcript_truncates_long_input() -> None:
    long_text = "x" * 200_000
    rendered = SummarizationService._format_transcript_for_prompt(
        full_text=long_text,
        segments=[],
    )
    assert len(rendered) < len(long_text)
    assert "truncated" in rendered


@pytest.mark.asyncio
async def test_generate_recap_happy_path(
    service: SummarizationService, session_id: uuid.UUID
) -> None:
    service.session_repo.get_by_id = AsyncMock(return_value=MagicMock(id=session_id))
    transcript = MagicMock()
    transcript.full_text = "Patient discussed anxiety about work."
    transcript.segments = []
    service.transcript_repo.get_transcript_by_session_id = AsyncMock(
        return_value=transcript
    )
    service.recap_repo.upsert = AsyncMock(return_value=_mock_recap_row(session_id))

    json_content = (
        '{"brief": "Discussed anxiety.", "key_topics": ["anxiety", "work"], '
        '"emotional_tone": "anxious", "homework_assigned": [], '
        '"follow_ups": [], "risk_flags": []}'
    )
    assert hasattr(service.claude_client, "chat")
    service.claude_client.chat = AsyncMock(  # type: ignore[method-assign]
        return_value=_mock_claude_response(json_content)
    )

    result = await service.generate_recap(session_id)

    assert result.brief == "A short recap."
    service.claude_client.chat.assert_awaited_once()
    service.recap_repo.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_recap_missing_session(
    service: SummarizationService, session_id: uuid.UUID
) -> None:
    service.session_repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.generate_recap(session_id)


@pytest.mark.asyncio
async def test_generate_recap_missing_transcript(
    service: SummarizationService, session_id: uuid.UUID
) -> None:
    service.session_repo.get_by_id = AsyncMock(return_value=MagicMock(id=session_id))
    service.transcript_repo.get_transcript_by_session_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.generate_recap(session_id)


@pytest.mark.asyncio
async def test_generate_recap_wraps_claude_errors(
    service: SummarizationService, session_id: uuid.UUID
) -> None:
    service.session_repo.get_by_id = AsyncMock(return_value=MagicMock(id=session_id))
    transcript = MagicMock()
    transcript.full_text = "text"
    transcript.segments = []
    service.transcript_repo.get_transcript_by_session_id = AsyncMock(
        return_value=transcript
    )
    service.claude_client.chat = AsyncMock(  # type: ignore[method-assign]
        side_effect=ClaudeError("boom")
    )

    with pytest.raises(SummarizationServiceError):
        await service.generate_recap(session_id)


@pytest.mark.asyncio
async def test_get_recap_returns_existing(
    service: SummarizationService, session_id: uuid.UUID
) -> None:
    service.recap_repo.get_by_session_id = AsyncMock(
        return_value=_mock_recap_row(session_id)
    )
    result = await service.get_recap(session_id)
    assert result.session_id == session_id


@pytest.mark.asyncio
async def test_get_recap_raises_when_absent(
    service: SummarizationService, session_id: uuid.UUID
) -> None:
    service.recap_repo.get_by_session_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.get_recap(session_id)
