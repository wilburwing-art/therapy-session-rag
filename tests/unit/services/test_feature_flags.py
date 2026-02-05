"""Unit tests for FeatureFlags service."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.db.experiment import ExperimentStatus
from src.services.feature_flags import FeatureFlags


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def flags(mock_session: AsyncMock) -> FeatureFlags:
    return FeatureFlags(mock_session)


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_running_experiment(name: str, org_id: uuid.UUID) -> MagicMock:
    exp = MagicMock()
    exp.id = uuid.uuid4()
    exp.name = name
    exp.status = ExperimentStatus.RUNNING
    exp.organization_id = org_id
    return exp


class TestIsEnabled:
    """Tests for is_enabled."""

    @pytest.mark.asyncio
    async def test_enabled_for_treatment_variant(
        self, flags: FeatureFlags, org_id: uuid.UUID
    ) -> None:
        exp = _make_running_experiment("feature_x", org_id)
        flags._repo.get_by_name = AsyncMock(return_value=exp)
        flags._service.assign_subject = AsyncMock(return_value="treatment")

        result = await flags.is_enabled("feature_x", uuid.uuid4(), org_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_disabled_for_control_variant(
        self, flags: FeatureFlags, org_id: uuid.UUID
    ) -> None:
        exp = _make_running_experiment("feature_x", org_id)
        flags._repo.get_by_name = AsyncMock(return_value=exp)
        flags._service.assign_subject = AsyncMock(return_value="control")

        result = await flags.is_enabled("feature_x", uuid.uuid4(), org_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_disabled_when_experiment_not_found(
        self, flags: FeatureFlags, org_id: uuid.UUID
    ) -> None:
        flags._repo.get_by_name = AsyncMock(return_value=None)

        result = await flags.is_enabled("nonexistent", uuid.uuid4(), org_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_disabled_when_experiment_not_running(
        self, flags: FeatureFlags, org_id: uuid.UUID
    ) -> None:
        exp = MagicMock()
        exp.status = ExperimentStatus.DRAFT
        flags._repo.get_by_name = AsyncMock(return_value=exp)

        result = await flags.is_enabled("draft_flag", uuid.uuid4(), org_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_disabled_on_assignment_error(
        self, flags: FeatureFlags, org_id: uuid.UUID
    ) -> None:
        exp = _make_running_experiment("feature_x", org_id)
        flags._repo.get_by_name = AsyncMock(return_value=exp)
        flags._service.assign_subject = AsyncMock(
            side_effect=Exception("not in traffic")
        )

        result = await flags.is_enabled("feature_x", uuid.uuid4(), org_id)

        assert result is False


class TestGetVariant:
    """Tests for get_variant."""

    @pytest.mark.asyncio
    async def test_returns_variant_name(
        self, flags: FeatureFlags, org_id: uuid.UUID
    ) -> None:
        exp = _make_running_experiment("ab_test", org_id)
        flags._repo.get_by_name = AsyncMock(return_value=exp)
        flags._service.assign_subject = AsyncMock(return_value="variant_b")

        result = await flags.get_variant("ab_test", uuid.uuid4(), org_id)

        assert result == "variant_b"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_experiment(
        self, flags: FeatureFlags, org_id: uuid.UUID
    ) -> None:
        flags._repo.get_by_name = AsyncMock(return_value=None)

        result = await flags.get_variant("nonexistent", uuid.uuid4(), org_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_error(
        self, flags: FeatureFlags, org_id: uuid.UUID
    ) -> None:
        exp = _make_running_experiment("ab_test", org_id)
        flags._repo.get_by_name = AsyncMock(return_value=exp)
        flags._service.assign_subject = AsyncMock(
            side_effect=Exception("traffic check")
        )

        result = await flags.get_variant("ab_test", uuid.uuid4(), org_id)

        assert result is None


class TestFindExperimentWithoutOrg:
    """Tests for cross-org flag lookup."""

    @pytest.mark.asyncio
    async def test_finds_by_name_across_orgs(
        self, flags: FeatureFlags
    ) -> None:
        org_id = uuid.uuid4()
        exp = _make_running_experiment("global_flag", org_id)
        flags._repo.list_by_org = AsyncMock(return_value=[exp])
        flags._service.assign_subject = AsyncMock(return_value="treatment")

        result = await flags.is_enabled("global_flag", uuid.uuid4())

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_match(
        self, flags: FeatureFlags
    ) -> None:
        flags._repo.list_by_org = AsyncMock(return_value=[])

        result = await flags.is_enabled("missing", uuid.uuid4())

        assert result is False
