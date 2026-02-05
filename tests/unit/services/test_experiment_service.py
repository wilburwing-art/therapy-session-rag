"""Unit tests for ExperimentService."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.db.experiment import Experiment, ExperimentAssignment, ExperimentStatus
from src.models.domain.experiment import ExperimentCreate, ExperimentUpdate
from src.services.experiment_service import ExperimentService, ExperimentServiceError


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_session: AsyncMock) -> ExperimentService:
    return ExperimentService(mock_session)


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_experiment(
    org_id: uuid.UUID,
    *,
    status: ExperimentStatus = ExperimentStatus.DRAFT,
    name: str = "test-exp",
    variants: dict | None = None,
    traffic_percentage: int = 100,
) -> MagicMock:
    exp = MagicMock(spec=Experiment)
    exp.id = uuid.uuid4()
    exp.name = name
    exp.description = "Test experiment"
    exp.status = status
    exp.organization_id = org_id
    exp.variants = variants or {"control": {}, "treatment": {"top_k": 10}}
    exp.targeting_rules = None
    exp.traffic_percentage = traffic_percentage
    exp.started_at = None
    exp.ended_at = None
    exp.created_at = datetime.now(UTC)
    exp.updated_at = datetime.now(UTC)
    return exp


class TestCreateExperiment:
    """Tests for experiment creation."""

    @pytest.mark.asyncio
    async def test_creates_experiment(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        data = ExperimentCreate(
            name="my-test",
            variants={"control": {}, "treatment": {"top_k": 10}},
        )
        service._repo.get_by_name = AsyncMock(return_value=None)
        mock_created = _make_experiment(org_id, name="my-test")
        service._repo.create = AsyncMock(return_value=mock_created)

        result = await service.create_experiment(data, org_id)

        assert result.name == "my-test"
        service._repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_fewer_than_two_variants(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        data = ExperimentCreate(
            name="bad",
            variants={"only_one": {}},
        )
        with pytest.raises(ExperimentServiceError, match="at least 2 variants"):
            await service.create_experiment(data, org_id)

    @pytest.mark.asyncio
    async def test_rejects_duplicate_name(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        data = ExperimentCreate(
            name="existing",
            variants={"a": {}, "b": {}},
        )
        service._repo.get_by_name = AsyncMock(
            return_value=_make_experiment(org_id, name="existing")
        )
        with pytest.raises(ExperimentServiceError, match="already exists"):
            await service.create_experiment(data, org_id)


class TestExperimentLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_draft_experiment(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.DRAFT)
        service._repo.get_by_id = AsyncMock(return_value=exp)

        await service.start_experiment(exp.id)

        assert exp.status == ExperimentStatus.RUNNING
        assert exp.started_at is not None

    @pytest.mark.asyncio
    async def test_cannot_start_running_experiment(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.RUNNING)
        service._repo.get_by_id = AsyncMock(return_value=exp)

        with pytest.raises(ExperimentServiceError, match="DRAFT"):
            await service.start_experiment(exp.id)

    @pytest.mark.asyncio
    async def test_stop_running_experiment(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.RUNNING)
        service._repo.get_by_id = AsyncMock(return_value=exp)

        await service.stop_experiment(exp.id)

        assert exp.status == ExperimentStatus.COMPLETED
        assert exp.ended_at is not None

    @pytest.mark.asyncio
    async def test_cannot_stop_draft_experiment(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.DRAFT)
        service._repo.get_by_id = AsyncMock(return_value=exp)

        with pytest.raises(ExperimentServiceError, match="RUNNING"):
            await service.stop_experiment(exp.id)

    @pytest.mark.asyncio
    async def test_start_nonexistent_experiment(
        self, service: ExperimentService
    ) -> None:
        service._repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ExperimentServiceError, match="not found"):
            await service.start_experiment(uuid.uuid4())


class TestUpdateExperiment:
    """Tests for updating experiments."""

    @pytest.mark.asyncio
    async def test_update_draft_experiment(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.DRAFT)
        service._repo.get_by_id = AsyncMock(return_value=exp)
        data = ExperimentUpdate(description="Updated description")

        await service.update_experiment(exp.id, data)

        assert exp.description == "Updated description"

    @pytest.mark.asyncio
    async def test_cannot_update_running_experiment(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.RUNNING)
        service._repo.get_by_id = AsyncMock(return_value=exp)
        data = ExperimentUpdate(description="nope")

        with pytest.raises(ExperimentServiceError, match="DRAFT"):
            await service.update_experiment(exp.id, data)


class TestAssignSubject:
    """Tests for subject assignment."""

    @pytest.mark.asyncio
    async def test_assigns_new_subject(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.RUNNING)
        service._repo.get_by_id = AsyncMock(return_value=exp)
        service._repo.get_assignment = AsyncMock(return_value=None)
        service._repo.create_assignment = AsyncMock()

        subject_id = uuid.uuid4()
        variant = await service.assign_subject(exp.id, subject_id)

        assert variant in ("control", "treatment")
        service._repo.create_assignment.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_existing_assignment(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.RUNNING)
        service._repo.get_by_id = AsyncMock(return_value=exp)
        existing = MagicMock(spec=ExperimentAssignment)
        existing.variant = "treatment"
        service._repo.get_assignment = AsyncMock(return_value=existing)
        service._repo.create_assignment = AsyncMock()

        variant = await service.assign_subject(exp.id, uuid.uuid4())

        assert variant == "treatment"
        service._repo.create_assignment.assert_not_called()

    @pytest.mark.asyncio
    async def test_cannot_assign_to_non_running(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.DRAFT)
        service._repo.get_by_id = AsyncMock(return_value=exp)

        with pytest.raises(ExperimentServiceError, match="not running"):
            await service.assign_subject(exp.id, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_deterministic_assignment(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        """Same experiment+subject always gets the same variant."""
        exp = _make_experiment(org_id, status=ExperimentStatus.RUNNING)
        exp_id = exp.id
        subject_id = uuid.uuid4()

        variant1 = ExperimentService._hash_assign(
            exp_id, subject_id, ["control", "treatment"]
        )
        variant2 = ExperimentService._hash_assign(
            exp_id, subject_id, ["control", "treatment"]
        )

        assert variant1 == variant2

    @pytest.mark.asyncio
    async def test_traffic_percentage_respected(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(
            org_id, status=ExperimentStatus.RUNNING, traffic_percentage=0
        )
        exp.traffic_percentage = 0
        service._repo.get_by_id = AsyncMock(return_value=exp)
        service._repo.get_assignment = AsyncMock(return_value=None)

        # 0% traffic means nobody gets in
        with pytest.raises(ExperimentServiceError, match="not in experiment traffic"):
            await service.assign_subject(exp.id, uuid.uuid4())


class TestGetResults:
    """Tests for results computation."""

    @pytest.mark.asyncio
    async def test_get_results_with_stats(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.RUNNING)
        service._repo.get_by_id = AsyncMock(return_value=exp)
        service._repo.get_metric_stats = AsyncMock(
            return_value=[
                ("control", 50, 3.2, 0.5, 1.0, 5.0),
                ("treatment", 50, 3.8, 0.6, 1.5, 5.5),
            ]
        )

        results = await service.get_results(exp.id, "conversion_rate")

        assert results.experiment_name == exp.name
        assert "control" in results.variant_stats
        assert "treatment" in results.variant_stats
        assert results.variant_stats["control"].subject_count == 50
        assert results.p_value is not None

    @pytest.mark.asyncio
    async def test_get_results_not_significant(
        self, service: ExperimentService, org_id: uuid.UUID
    ) -> None:
        exp = _make_experiment(org_id, status=ExperimentStatus.RUNNING)
        service._repo.get_by_id = AsyncMock(return_value=exp)
        # Same means, should not be significant
        service._repo.get_metric_stats = AsyncMock(
            return_value=[
                ("control", 50, 3.5, 0.5, 1.0, 5.0),
                ("treatment", 50, 3.5, 0.5, 1.0, 5.0),
            ]
        )

        results = await service.get_results(exp.id, "metric")

        assert results.is_significant is False
        assert results.p_value is not None
        assert results.p_value > 0.05

    @pytest.mark.asyncio
    async def test_get_results_nonexistent_experiment(
        self, service: ExperimentService
    ) -> None:
        service._repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ExperimentServiceError, match="not found"):
            await service.get_results(uuid.uuid4(), "metric")


class TestHashAssign:
    """Tests for the static hash assignment method."""

    def test_distributes_across_variants(self) -> None:
        exp_id = uuid.uuid4()
        variants = ["a", "b", "c"]
        assignments: dict[str, int] = dict.fromkeys(variants, 0)

        for i in range(300):
            subject = uuid.UUID(int=i)
            v = ExperimentService._hash_assign(exp_id, subject, variants)
            assignments[v] += 1

        # Each variant should get roughly 100 assignments
        for count in assignments.values():
            assert count > 50, f"Variant got too few assignments: {count}"


class TestIsInTraffic:
    """Tests for traffic bucketing."""

    def test_100_percent_always_in(self) -> None:
        assert ExperimentService._is_in_traffic(uuid.uuid4(), uuid.uuid4(), 100) is True

    def test_0_percent_never_in(self) -> None:
        # Test with many subjects — none should be in traffic at 0%
        exp_id = uuid.uuid4()
        for i in range(50):
            assert ExperimentService._is_in_traffic(
                exp_id, uuid.UUID(int=i), 0
            ) is False


class TestWelchTTest:
    """Tests for the Welch's t-test implementation."""

    def test_identical_means_high_p_value(self) -> None:
        p = ExperimentService._welch_t_test(3.0, 1.0, 100, 3.0, 1.0, 100)
        assert p > 0.9

    def test_different_means_low_p_value(self) -> None:
        p = ExperimentService._welch_t_test(1.0, 0.5, 100, 5.0, 0.5, 100)
        assert p < 0.001

    def test_zero_std_equal_means(self) -> None:
        p = ExperimentService._welch_t_test(3.0, 0.0, 10, 3.0, 0.0, 10)
        assert p == 1.0

    def test_zero_std_different_means(self) -> None:
        p = ExperimentService._welch_t_test(3.0, 0.0, 10, 5.0, 0.0, 10)
        assert p == 0.0
