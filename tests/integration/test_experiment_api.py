"""Integration tests for Experiment API endpoints with live database."""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.experiment import Experiment, ExperimentStatus
from src.models.db.organization import Organization


@pytest_asyncio.fixture(loop_scope="session")
async def experiment(db_session: AsyncSession, test_org: Organization) -> Experiment:
    """Create a DRAFT experiment in the database."""
    exp = Experiment(
        id=uuid.uuid4(),
        name=f"test-exp-{uuid.uuid4().hex[:8]}",
        description="Integration test experiment",
        status=ExperimentStatus.DRAFT,
        organization_id=test_org.id,
        variants={"control": {}, "treatment": {"top_k": 10}},
        targeting_rules=None,
        traffic_percentage=100,
    )
    db_session.add(exp)
    await db_session.flush()
    await db_session.refresh(exp)
    return exp


@pytest.mark.integration
class TestExperimentCRUD:
    """Integration tests for experiment CRUD operations."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_experiment(self, async_client: AsyncClient) -> None:
        response = await async_client.post(
            "/api/v1/experiments",
            json={
                "name": f"integ-test-{uuid.uuid4().hex[:8]}",
                "description": "Created via integration test",
                "variants": {"control": {}, "treatment": {"top_k": 5}},
                "traffic_percentage": 50,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["traffic_percentage"] == 50
        assert "control" in data["variants"]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_list_experiments(
        self, async_client: AsyncClient, experiment: Experiment
    ) -> None:
        response = await async_client.get("/api/v1/experiments")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_experiment_by_id(
        self, async_client: AsyncClient, experiment: Experiment
    ) -> None:
        response = await async_client.get(f"/api/v1/experiments/{experiment.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == experiment.name

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_nonexistent_experiment(self, async_client: AsyncClient) -> None:
        response = await async_client.get(f"/api/v1/experiments/{uuid.uuid4()}")

        assert response.status_code == 404

    @pytest.mark.asyncio(loop_scope="session")
    async def test_update_draft_experiment(
        self, async_client: AsyncClient, experiment: Experiment
    ) -> None:
        response = await async_client.patch(
            f"/api/v1/experiments/{experiment.id}",
            json={"description": "Updated via integration test"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_duplicate_name_fails(
        self, async_client: AsyncClient, experiment: Experiment
    ) -> None:
        response = await async_client.post(
            "/api/v1/experiments",
            json={
                "name": experiment.name,
                "variants": {"a": {}, "b": {}},
            },
        )

        assert response.status_code == 409

    @pytest.mark.asyncio(loop_scope="session")
    async def test_filter_by_status(self, async_client: AsyncClient) -> None:
        response = await async_client.get(
            "/api/v1/experiments",
            params={"status": "running"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["status"] == "running" for e in data)


@pytest.mark.integration
class TestExperimentLifecycle:
    """Integration tests for experiment start/stop lifecycle."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_start_and_stop_experiment(
        self, async_client: AsyncClient, experiment: Experiment
    ) -> None:
        # Start
        response = await async_client.post(
            f"/api/v1/experiments/{experiment.id}/start"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "running"

        # Stop
        response = await async_client.post(
            f"/api/v1/experiments/{experiment.id}/stop"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_cannot_start_running_experiment(
        self, async_client: AsyncClient, experiment: Experiment
    ) -> None:
        await async_client.post(f"/api/v1/experiments/{experiment.id}/start")
        response = await async_client.post(
            f"/api/v1/experiments/{experiment.id}/start"
        )

        assert response.status_code == 400


@pytest.mark.integration
class TestExperimentAssignment:
    """Integration tests for subject assignment and metrics."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_assign_subject_to_running_experiment(
        self, async_client: AsyncClient, experiment: Experiment
    ) -> None:
        # Start the experiment first
        await async_client.post(f"/api/v1/experiments/{experiment.id}/start")

        subject_id = uuid.uuid4()
        response = await async_client.post(
            f"/api/v1/experiments/{experiment.id}/assign/{subject_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["variant"] in ("control", "treatment")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_consistent_assignment(
        self, async_client: AsyncClient, experiment: Experiment
    ) -> None:
        await async_client.post(f"/api/v1/experiments/{experiment.id}/start")

        subject_id = uuid.uuid4()
        r1 = await async_client.post(
            f"/api/v1/experiments/{experiment.id}/assign/{subject_id}"
        )
        r2 = await async_client.post(
            f"/api/v1/experiments/{experiment.id}/assign/{subject_id}"
        )

        assert r1.json()["variant"] == r2.json()["variant"]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_record_metric(
        self, async_client: AsyncClient, experiment: Experiment
    ) -> None:
        await async_client.post(f"/api/v1/experiments/{experiment.id}/start")

        subject_id = uuid.uuid4()
        await async_client.post(
            f"/api/v1/experiments/{experiment.id}/assign/{subject_id}"
        )

        response = await async_client.post(
            f"/api/v1/experiments/{experiment.id}/metrics",
            json={
                "subject_id": str(subject_id),
                "metric_name": "conversion",
                "metric_value": 1.0,
            },
        )

        assert response.status_code == 201
        assert response.json()["status"] == "recorded"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_results(
        self, async_client: AsyncClient, experiment: Experiment
    ) -> None:
        await async_client.post(f"/api/v1/experiments/{experiment.id}/start")

        # Assign and record metrics for several subjects
        for i in range(10):
            subject_id = uuid.UUID(int=i)
            await async_client.post(
                f"/api/v1/experiments/{experiment.id}/assign/{subject_id}"
            )
            await async_client.post(
                f"/api/v1/experiments/{experiment.id}/metrics",
                json={
                    "subject_id": str(subject_id),
                    "metric_name": "score",
                    "metric_value": float(i),
                },
            )

        response = await async_client.get(
            f"/api/v1/experiments/{experiment.id}/results",
            params={"metric_name": "score"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["experiment_name"] == experiment.name
        assert len(data["variant_stats"]) > 0


@pytest.mark.integration
class TestExperimentAuth:
    """Integration tests for authentication on experiment endpoints."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_requires_api_key(self, async_client: AsyncClient) -> None:
        # Remove API key header
        client = async_client
        original_headers = dict(client.headers)
        client.headers.pop("X-API-Key", None)

        response = await client.get("/api/v1/experiments")

        # Restore headers
        client.headers.update(original_headers)
        assert response.status_code == 401
