"""Unit tests for Experiment API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth, get_event_publisher
from src.api.v1.endpoints.experiments import get_experiment_service, router
from src.core.database import get_db_session
from src.models.domain.experiment import (
    ExperimentRead,
    ExperimentResults,
    VariantStats,
)
from src.services.experiment_service import ExperimentServiceError


@pytest.fixture
def mock_auth_context() -> MagicMock:
    ctx = MagicMock()
    ctx.api_key_id = uuid.uuid4()
    ctx.organization_id = uuid.uuid4()
    ctx.api_key_name = "test-key"
    return ctx


@pytest.fixture
def mock_experiment_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def app(mock_auth_context: MagicMock, mock_experiment_service: MagicMock) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/experiments")

    mock_events = MagicMock()
    mock_events.publish = AsyncMock(return_value=None)

    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_experiment_service] = lambda: mock_experiment_service
    test_app.dependency_overrides[get_event_publisher] = lambda: mock_events

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _make_experiment_read(org_id: uuid.UUID, name: str = "test-exp") -> ExperimentRead:
    return ExperimentRead(
        id=uuid.uuid4(),
        name=name,
        description="A test experiment",
        status="draft",
        organization_id=org_id,
        variants={"control": {}, "treatment": {"top_k": 10}},
        targeting_rules=None,
        traffic_percentage=100,
        started_at=None,
        ended_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestCreateExperiment:
    """Tests for POST /experiments."""

    def test_create_experiment(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        exp = _make_experiment_read(mock_auth_context.organization_id)
        mock_experiment_service.create_experiment = AsyncMock(return_value=exp)

        response = client.post(
            "/experiments",
            json={
                "name": "test-exp",
                "variants": {"control": {}, "treatment": {"top_k": 10}},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-exp"
        assert data["status"] == "draft"

    def test_create_duplicate_returns_409(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        mock_experiment_service.create_experiment = AsyncMock(
            side_effect=ExperimentServiceError("already exists")
        )

        response = client.post(
            "/experiments",
            json={
                "name": "dup",
                "variants": {"a": {}, "b": {}},
            },
        )

        assert response.status_code == 409


class TestListExperiments:
    """Tests for GET /experiments."""

    def test_list_experiments(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        exp = _make_experiment_read(mock_auth_context.organization_id)
        mock_experiment_service.list_experiments = AsyncMock(return_value=[exp])

        response = client.get("/experiments")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_list_experiments_with_status_filter(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        mock_experiment_service.list_experiments = AsyncMock(return_value=[])

        response = client.get("/experiments", params={"status": "running"})

        assert response.status_code == 200
        call_kwargs = mock_experiment_service.list_experiments.call_args.kwargs
        assert call_kwargs["status"].value == "running"

    def test_list_experiments_empty(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        mock_experiment_service.list_experiments = AsyncMock(return_value=[])

        response = client.get("/experiments")

        assert response.status_code == 200
        assert response.json() == []


class TestGetExperiment:
    """Tests for GET /experiments/{id}."""

    def test_get_experiment(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        exp = _make_experiment_read(mock_auth_context.organization_id)
        mock_experiment_service.get_experiment = AsyncMock(return_value=exp)

        response = client.get(f"/experiments/{exp.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "test-exp"

    def test_get_experiment_not_found(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        mock_experiment_service.get_experiment = AsyncMock(return_value=None)

        response = client.get(f"/experiments/{uuid.uuid4()}")

        assert response.status_code == 404


class TestUpdateExperiment:
    """Tests for PATCH /experiments/{id}."""

    def test_update_experiment(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        exp = _make_experiment_read(mock_auth_context.organization_id)
        mock_experiment_service.update_experiment = AsyncMock(return_value=exp)

        response = client.patch(
            f"/experiments/{exp.id}",
            json={"description": "Updated"},
        )

        assert response.status_code == 200

    def test_update_non_draft_returns_400(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        mock_experiment_service.update_experiment = AsyncMock(
            side_effect=ExperimentServiceError("Can only update DRAFT")
        )

        response = client.patch(
            f"/experiments/{uuid.uuid4()}",
            json={"description": "nope"},
        )

        assert response.status_code == 400


class TestStartStopExperiment:
    """Tests for POST /experiments/{id}/start and /stop."""

    def test_start_experiment(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        exp = _make_experiment_read(mock_auth_context.organization_id)
        mock_experiment_service.start_experiment = AsyncMock(return_value=exp)

        response = client.post(f"/experiments/{exp.id}/start")

        assert response.status_code == 200

    def test_start_non_draft_returns_400(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        mock_experiment_service.start_experiment = AsyncMock(
            side_effect=ExperimentServiceError("Can only start DRAFT")
        )

        response = client.post(f"/experiments/{uuid.uuid4()}/start")

        assert response.status_code == 400

    def test_stop_experiment(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        exp = _make_experiment_read(mock_auth_context.organization_id)
        mock_experiment_service.stop_experiment = AsyncMock(return_value=exp)

        response = client.post(f"/experiments/{exp.id}/stop")

        assert response.status_code == 200


class TestAssignSubject:
    """Tests for POST /experiments/{id}/assign/{subject_id}."""

    def test_assign_subject(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        mock_experiment_service.assign_subject = AsyncMock(return_value="treatment")

        response = client.post(
            f"/experiments/{uuid.uuid4()}/assign/{uuid.uuid4()}"
        )

        assert response.status_code == 200
        assert response.json()["variant"] == "treatment"

    def test_assign_subject_error(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        mock_experiment_service.assign_subject = AsyncMock(
            side_effect=ExperimentServiceError("not running")
        )

        response = client.post(
            f"/experiments/{uuid.uuid4()}/assign/{uuid.uuid4()}"
        )

        assert response.status_code == 400


class TestRecordMetric:
    """Tests for POST /experiments/{id}/metrics."""

    def test_record_metric(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        mock_experiment_service.record_metric = AsyncMock()

        response = client.post(
            f"/experiments/{uuid.uuid4()}/metrics",
            json={
                "subject_id": str(uuid.uuid4()),
                "metric_name": "conversion",
                "metric_value": 1.0,
            },
        )

        assert response.status_code == 201
        assert response.json()["status"] == "recorded"


class TestGetResults:
    """Tests for GET /experiments/{id}/results."""

    def test_get_results(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        exp_id = uuid.uuid4()
        mock_results = ExperimentResults(
            experiment_id=exp_id,
            experiment_name="test",
            status="running",
            variant_stats={
                "control": VariantStats(
                    variant_name="control",
                    subject_count=50,
                    metric_mean=3.2,
                    metric_std=0.5,
                    metric_min=1.0,
                    metric_max=5.0,
                ),
                "treatment": VariantStats(
                    variant_name="treatment",
                    subject_count=50,
                    metric_mean=3.8,
                    metric_std=0.6,
                    metric_min=1.5,
                    metric_max=5.5,
                ),
            },
            is_significant=True,
            p_value=0.001,
            confidence_level=0.95,
        )
        mock_experiment_service.get_results = AsyncMock(return_value=mock_results)

        response = client.get(
            f"/experiments/{exp_id}/results",
            params={"metric_name": "conversion"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_significant"] is True
        assert "control" in data["variant_stats"]
        assert "treatment" in data["variant_stats"]

    def test_get_results_not_found(
        self,
        client: TestClient,
        mock_experiment_service: MagicMock,
    ) -> None:
        mock_experiment_service.get_results = AsyncMock(
            side_effect=ExperimentServiceError("not found")
        )

        response = client.get(
            f"/experiments/{uuid.uuid4()}/results",
            params={"metric_name": "metric"},
        )

        assert response.status_code == 404

    def test_get_results_requires_metric_name(
        self,
        client: TestClient,
    ) -> None:
        response = client.get(f"/experiments/{uuid.uuid4()}/results")

        assert response.status_code == 422
