"""Tests for ThemesService."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.models.db.patient_themes import PatientThemes
from src.services.claude_client import ChatResponse, ClaudeError
from src.services.themes_service import ThemesService, ThemesServiceError


def _mock_claude_response(content: str, model: str = "claude-sonnet-4-test") -> ChatResponse:
    return ChatResponse(
        content=content,
        model=model,
        input_tokens=200,
        output_tokens=100,
        stop_reason="end_turn",
    )


def _mock_recap(brief: str, topics: list[str]) -> MagicMock:
    r = MagicMock()
    r.brief = brief
    r.key_topics = topics
    r.emotional_tone = "reflective"
    r.homework_assigned = [{"task": "Journal nightly", "notes": None}]
    r.follow_ups = []
    r.risk_flags = []
    return r


def _mock_themes_row(patient_id: uuid.UUID) -> PatientThemes:
    row = MagicMock(spec=PatientThemes)
    row.id = uuid.uuid4()
    row.patient_id = patient_id
    row.recurring_topics = [{"topic": "work anxiety", "session_count": 2, "summary": None}]
    row.emotional_patterns = [{"pattern": "rumination", "evidence": None}]
    row.coping_strategies = []
    row.progress_indicators = ["Started journaling consistently"]
    row.ongoing_concerns = ["Sleep disruption"]
    row.source_session_count = 3
    row.model_name = "claude-sonnet-4-test"
    row.generated_at = datetime.now(UTC)
    row.created_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    return row


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def service() -> ThemesService:
    svc = ThemesService(db_session=MagicMock(), claude_client=MagicMock())
    svc.repo = MagicMock()
    svc.claude_client.chat = AsyncMock()  # type: ignore[method-assign]
    return svc


def test_parse_payload_happy() -> None:
    raw = '{"recurring_topics": [], "emotional_patterns": [], "coping_strategies": [], "progress_indicators": [], "ongoing_concerns": []}'
    result = ThemesService._parse_payload(raw)
    assert result.recurring_topics == []


def test_parse_payload_with_fence() -> None:
    raw = '```json\n{"recurring_topics": [{"topic": "grief", "session_count": 3, "summary": null}], "emotional_patterns": [], "coping_strategies": [], "progress_indicators": [], "ongoing_concerns": []}\n```'
    result = ThemesService._parse_payload(raw)
    assert result.recurring_topics[0].topic == "grief"


def test_parse_payload_raises_on_bad_json() -> None:
    with pytest.raises(ThemesServiceError):
        ThemesService._parse_payload("totally not json")


def test_format_recaps_renders_all_fields() -> None:
    recaps = [_mock_recap("First session brief", ["anxiety", "work"])]
    rendered = ThemesService._format_recaps(recaps)
    assert "First session brief" in rendered
    assert "anxiety, work" in rendered
    assert "reflective" in rendered
    assert "Journal nightly" in rendered


@pytest.mark.asyncio
async def test_generate_themes_requires_minimum_recaps(
    service: ThemesService, patient_id: uuid.UUID
) -> None:
    service.repo.list_recaps_for_patient = AsyncMock(return_value=[_mock_recap("solo", ["x"])])
    with pytest.raises(ThemesServiceError):
        await service.generate_themes(patient_id)


@pytest.mark.asyncio
async def test_generate_themes_happy_path(service: ThemesService, patient_id: uuid.UUID) -> None:
    service.repo.list_recaps_for_patient = AsyncMock(
        return_value=[
            _mock_recap("Session 1", ["anxiety"]),
            _mock_recap("Session 2", ["anxiety", "sleep"]),
        ]
    )
    service.repo.upsert = AsyncMock(return_value=_mock_themes_row(patient_id))

    json_content = (
        '{"recurring_topics": [{"topic": "anxiety", "session_count": 2, "summary": null}], '
        '"emotional_patterns": [], "coping_strategies": [], '
        '"progress_indicators": [], "ongoing_concerns": []}'
    )
    service.claude_client.chat = AsyncMock(  # type: ignore[method-assign]
        return_value=_mock_claude_response(json_content)
    )

    result = await service.generate_themes(patient_id)
    assert result.patient_id == patient_id
    assert result.source_session_count == 3
    service.claude_client.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_themes_wraps_claude_errors(
    service: ThemesService, patient_id: uuid.UUID
) -> None:
    service.repo.list_recaps_for_patient = AsyncMock(
        return_value=[_mock_recap("a", ["x"]), _mock_recap("b", ["y"])]
    )
    service.claude_client.chat = AsyncMock(  # type: ignore[method-assign]
        side_effect=ClaudeError("rate limit")
    )
    with pytest.raises(ThemesServiceError):
        await service.generate_themes(patient_id)


@pytest.mark.asyncio
async def test_get_themes_missing_raises(service: ThemesService, patient_id: uuid.UUID) -> None:
    service.repo.get_by_patient_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.get_themes(patient_id)


@pytest.mark.asyncio
async def test_get_themes_returns_existing(service: ThemesService, patient_id: uuid.UUID) -> None:
    service.repo.get_by_patient_id = AsyncMock(return_value=_mock_themes_row(patient_id))
    result = await service.get_themes(patient_id)
    assert result.patient_id == patient_id
    assert result.source_session_count == 3
