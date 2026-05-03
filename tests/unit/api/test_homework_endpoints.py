"""Unit tests for homework API endpoints.

Covers both the patient-facing ``/homework/*`` surface and the
therapist-facing ``/patients/{id}/homework`` read. Services mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import (
    get_api_key_auth,
    get_current_patient,
    get_event_publisher,
)
from src.api.v1.endpoints.homework import (
    get_homework_service as get_patient_homework_service,
)
from src.api.v1.endpoints.homework import (
    router as homework_router,
)
from src.api.v1.endpoints.patients import (
    get_homework_service as get_therapist_homework_service,
)
from src.api.v1.endpoints.patients import (
    router as patients_router,
)
from src.core.database import get_db_session
from src.core.exceptions import NotFoundError, setup_exception_handlers
from src.models.domain.homework import HomeworkItemRead


def _make_homework_read(
    patient_id: uuid.UUID,
    task: str = "Journal nightly",
    completed: bool = False,
) -> HomeworkItemRead:
    now = datetime(2026, 4, 21, 10, 0, 0, tzinfo=UTC)
    return HomeworkItemRead(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        patient_id=patient_id,
        task=task,
        notes=None,
        completed=completed,
        completed_at=now if completed else None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_auth_context(org_id: uuid.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.api_key_id = uuid.uuid4()
    ctx.organization_id = org_id
    ctx.api_key_name = "therapist"
    return ctx


@pytest.fixture
def mock_patient_user(org_id: uuid.UUID, patient_id: uuid.UUID) -> MagicMock:
    user = MagicMock()
    user.id = patient_id
    user.organization_id = org_id
    user.email = "patient@example.com"
    return user


@pytest.fixture
def mock_homework_service() -> MagicMock:
    svc = MagicMock()
    svc.list_for_patient = AsyncMock()
    svc.toggle_completion = AsyncMock()
    return svc


@pytest.fixture
def patient_app(
    mock_patient_user: MagicMock,
    mock_homework_service: MagicMock,
) -> FastAPI:
    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(homework_router, prefix="/homework")

    mock_events = MagicMock()
    mock_events.publish = AsyncMock(return_value=None)

    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_patient] = lambda: mock_patient_user
    app.dependency_overrides[get_event_publisher] = lambda: mock_events
    app.dependency_overrides[get_patient_homework_service] = (
        lambda: mock_homework_service
    )
    return app


@pytest.fixture
def patient_client(patient_app: FastAPI) -> TestClient:
    return TestClient(patient_app)


@pytest.fixture
def therapist_app(
    mock_auth_context: MagicMock,
    mock_homework_service: MagicMock,
) -> FastAPI:
    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(patients_router, prefix="/patients")

    mock_events = MagicMock()
    mock_events.publish = AsyncMock(return_value=None)

    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    app.dependency_overrides[get_event_publisher] = lambda: mock_events
    app.dependency_overrides[get_therapist_homework_service] = (
        lambda: mock_homework_service
    )
    return app


@pytest.fixture
def therapist_client(therapist_app: FastAPI) -> TestClient:
    return TestClient(therapist_app)


class TestPatientListMyHomework:
    def test_list_returns_items(
        self,
        patient_client: TestClient,
        mock_homework_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_homework_service.list_for_patient.return_value = [
            _make_homework_read(patient_id, task="A"),
            _make_homework_read(patient_id, task="B", completed=True),
        ]

        response = patient_client.get("/homework/me")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["task"] == "A"
        assert body[1]["completed"] is True

    def test_list_respects_completed_filter(
        self,
        patient_client: TestClient,
        mock_homework_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_homework_service.list_for_patient.return_value = []

        response = patient_client.get("/homework/me?completed=false&limit=10")

        assert response.status_code == 200
        _, kwargs = mock_homework_service.list_for_patient.call_args
        assert kwargs["patient_id"] == patient_id
        assert kwargs["completed"] is False
        assert kwargs["limit"] == 10


class TestPatientToggleHomework:
    def test_toggle_success(
        self,
        patient_client: TestClient,
        mock_homework_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        updated = _make_homework_read(patient_id, completed=True)
        mock_homework_service.toggle_completion.return_value = updated

        response = patient_client.patch(
            f"/homework/{updated.id}",
            json={"completed": True},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(updated.id)
        assert body["completed"] is True
        _, kwargs = mock_homework_service.toggle_completion.call_args
        assert kwargs["patient_id"] == patient_id
        assert kwargs["completed"] is True

    def test_toggle_not_found_returns_404(
        self,
        patient_client: TestClient,
        mock_homework_service: MagicMock,
    ) -> None:
        mock_homework_service.toggle_completion.side_effect = NotFoundError(
            resource="HomeworkItem"
        )

        response = patient_client.patch(
            f"/homework/{uuid.uuid4()}",
            json={"completed": True},
        )

        assert response.status_code == 404


class TestTherapistListPatientHomework:
    def test_list_scoped_to_org(
        self,
        therapist_client: TestClient,
        mock_homework_service: MagicMock,
        mock_auth_context: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_homework_service.list_for_patient.return_value = [
            _make_homework_read(patient_id, task="Read chapter"),
        ]

        response = therapist_client.get(f"/patients/{patient_id}/homework")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["task"] == "Read chapter"
        _, kwargs = mock_homework_service.list_for_patient.call_args
        assert kwargs["patient_id"] == patient_id
        assert kwargs["organization_id"] == mock_auth_context.organization_id
        assert kwargs["limit"] == 100

    def test_list_honors_completed_filter(
        self,
        therapist_client: TestClient,
        mock_homework_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_homework_service.list_for_patient.return_value = []

        response = therapist_client.get(
            f"/patients/{patient_id}/homework?completed=true&limit=25"
        )

        assert response.status_code == 200
        _, kwargs = mock_homework_service.list_for_patient.call_args
        assert kwargs["completed"] is True
        assert kwargs["limit"] == 25
