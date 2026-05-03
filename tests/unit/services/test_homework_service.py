"""Tests for HomeworkService."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.models.db.homework_item import HomeworkItem
from src.repositories.homework_repo import HomeworkRepository
from src.services.homework_service import HomeworkService


def _mock_row(
    patient_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
    task: str = "Journal nightly",
    notes: str | None = None,
    completed: bool = False,
) -> HomeworkItem:
    row = MagicMock(spec=HomeworkItem)
    row.id = uuid.uuid4()
    row.session_id = session_id or uuid.uuid4()
    row.patient_id = patient_id
    row.task = task
    row.notes = notes
    row.completed = completed
    row.completed_at = datetime.now(UTC) if completed else None
    row.created_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    return row


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def service() -> HomeworkService:
    svc = HomeworkService(db_session=MagicMock())
    svc.repo = MagicMock(spec=HomeworkRepository)
    return svc


def test_hash_task_is_stable_and_case_insensitive() -> None:
    a = HomeworkRepository.hash_task("Journal nightly")
    b = HomeworkRepository.hash_task("  journal   NIGHTLY  ")
    c = HomeworkRepository.hash_task("journal nightly")
    assert a == b == c
    assert len(a) == 64


def test_hash_task_differentiates_distinct_tasks() -> None:
    a = HomeworkRepository.hash_task("Journal nightly")
    b = HomeworkRepository.hash_task("Journal weekly")
    assert a != b


@pytest.mark.asyncio
async def test_materialize_from_recap_empty_is_noop(
    service: HomeworkService,
) -> None:
    created = await service.materialize_from_recap(
        session_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        homework_assigned=[],
    )
    assert created == 0


@pytest.mark.asyncio
async def test_materialize_from_recap_delegates_to_repo(
    service: HomeworkService,
) -> None:
    service.repo.upsert_many_for_session = AsyncMock(return_value=2)
    session_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    org_id = uuid.uuid4()
    items = [
        {"task": "Journal nightly", "notes": None},
        {"task": "Practice breathing", "notes": "5 min morning"},
    ]

    count = await service.materialize_from_recap(
        session_id=session_id,
        patient_id=patient_id,
        organization_id=org_id,
        homework_assigned=items,
    )

    assert count == 2
    service.repo.upsert_many_for_session.assert_awaited_once_with(
        session_id=session_id,
        patient_id=patient_id,
        organization_id=org_id,
        items=items,
    )


@pytest.mark.asyncio
async def test_list_for_patient_maps_rows_to_read(
    service: HomeworkService, patient_id: uuid.UUID
) -> None:
    service.repo.list_for_patient = AsyncMock(
        return_value=[
            _mock_row(patient_id, task="A"),
            _mock_row(patient_id, task="B", completed=True),
        ]
    )

    items = await service.list_for_patient(patient_id=patient_id)

    assert len(items) == 2
    assert items[0].task == "A"
    assert items[1].task == "B"
    assert items[1].completed is True


@pytest.mark.asyncio
async def test_list_for_patient_filters_by_completed(
    service: HomeworkService, patient_id: uuid.UUID
) -> None:
    service.repo.list_for_patient = AsyncMock(return_value=[])
    await service.list_for_patient(
        patient_id=patient_id,
        organization_id=uuid.uuid4(),
        completed=False,
        limit=25,
    )
    _, kwargs = service.repo.list_for_patient.call_args
    assert kwargs["completed"] is False
    assert kwargs["limit"] == 25


@pytest.mark.asyncio
async def test_toggle_completion_success(service: HomeworkService, patient_id: uuid.UUID) -> None:
    row = _mock_row(patient_id, completed=True)
    service.repo.set_completed = AsyncMock(return_value=row)

    result = await service.toggle_completion(
        homework_id=row.id,
        patient_id=patient_id,
        completed=True,
    )

    assert result.id == row.id
    assert result.completed is True
    service.repo.set_completed.assert_awaited_once_with(
        homework_id=row.id,
        patient_id=patient_id,
        completed=True,
    )


@pytest.mark.asyncio
async def test_toggle_completion_missing_raises(
    service: HomeworkService, patient_id: uuid.UUID
) -> None:
    service.repo.set_completed = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.toggle_completion(
            homework_id=uuid.uuid4(),
            patient_id=patient_id,
            completed=True,
        )
