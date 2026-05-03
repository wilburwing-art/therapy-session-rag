"""Tests for src.cli.admin."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.cli import admin as cli_admin
from src.cli.admin import AdminRow, _render_csv, _render_table


def _make_row(
    email: str = "admin@example.com",
    full_name: str | None = "Admin User",
    organization_name: str = "Acme Therapy",
    last_login: datetime | None = None,
    dormant: bool = False,
) -> AdminRow:
    return AdminRow(
        user_id=uuid.uuid4(),
        email=email,
        full_name=full_name,
        organization_name=organization_name,
        last_login_at=last_login,
        dormant=dormant,
    )


class TestRenderers:
    def test_render_csv_writes_header_and_rows(self) -> None:
        buf = io.StringIO()
        rows = [
            _make_row(
                email="a@example.com",
                last_login=datetime(2026, 4, 1, tzinfo=UTC),
                dormant=False,
            ),
            _make_row(
                email="b@example.com",
                full_name=None,
                organization_name="Other Org",
                last_login=None,
                dormant=True,
            ),
        ]
        _render_csv(rows, buf)
        out = buf.getvalue().splitlines()
        assert out[0] == "email,full_name,organization,last_login_at,dormant"
        assert out[1].startswith("a@example.com,Admin User,Acme Therapy,2026-04-01")
        assert out[1].endswith(",false")
        assert out[2] == "b@example.com,,Other Org,,true"

    def test_render_table_empty(self) -> None:
        buf = io.StringIO()
        _render_table([], buf)
        assert buf.getvalue().strip() == "No admin users found."

    def test_render_table_includes_never_for_missing_login(self) -> None:
        buf = io.StringIO()
        _render_table([_make_row(last_login=None, dormant=True)], buf)
        text = buf.getvalue()
        assert "never" in text
        assert "yes" in text  # dormant column


class TestDispatch:
    def test_help_prints_without_stacktrace(self, capsys: pytest.CaptureFixture[str]) -> None:
        # argparse exits with SystemExit(0) on --help. Verify it does so
        # cleanly — no stack trace, no asyncio loop spun up.
        with pytest.raises(SystemExit) as exc_info:
            cli_admin.main(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "therapyrag-admin" in captured.out
        assert "access-review" in captured.out
        assert "retention-purge" in captured.out

    def test_access_review_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            cli_admin.main(["access-review", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "--organization-id" in captured.out
        assert "--csv" in captured.out

    def test_retention_purge_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            cli_admin.main(["retention-purge", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "--days" in captured.out
        assert "--dry-run" in captured.out

    def test_missing_command_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            cli_admin.main([])

    def test_access_review_rejects_bad_org_uuid(self) -> None:
        # The inner async runner must return a non-zero exit code and
        # never touch the database for a malformed org id.
        with patch.object(cli_admin, "_make_session_factory") as factory:
            rc = cli_admin.main(["access-review", "--organization-id", "not-a-uuid"])
        assert rc == 2
        factory.assert_not_called()


class TestDormancyClassification:
    """Unit test for the dormancy cutoff logic without a live DB.

    We test ``_collect_admin_rows``'s pure classification by feeding in a
    mock session whose execute() returns shaped rows. Keeps the test
    hermetic.
    """

    async def test_never_logged_in_is_dormant(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        session = MagicMock()
        # First execute(): users JOIN organizations
        user = MagicMock(id=uuid.uuid4(), email="a@x.com", full_name="A")
        users_result = MagicMock()
        users_result.all.return_value = [(user, "Org A")]
        # Second execute(): max(event_timestamp) group by actor_id → no rows
        login_result = MagicMock()
        login_result.all.return_value = []

        session.execute = AsyncMock(side_effect=[users_result, login_result])

        rows = await cli_admin._collect_admin_rows(session, organization_id=None)
        assert len(rows) == 1
        assert rows[0].last_login_at is None
        assert rows[0].dormant is True

    async def test_recent_login_is_not_dormant(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        session = MagicMock()
        user_id = uuid.uuid4()
        user = MagicMock(id=user_id, email="a@x.com", full_name="A")
        users_result = MagicMock()
        users_result.all.return_value = [(user, "Org A")]

        recent = datetime.now(UTC) - timedelta(days=5)
        login_row = MagicMock(actor_id=user_id, last_login=recent)
        login_result = MagicMock()
        login_result.all.return_value = [login_row]

        session.execute = AsyncMock(side_effect=[users_result, login_result])

        rows = await cli_admin._collect_admin_rows(session, organization_id=None)
        assert len(rows) == 1
        assert rows[0].last_login_at == recent
        assert rows[0].dormant is False

    async def test_old_login_is_dormant(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        session = MagicMock()
        user_id = uuid.uuid4()
        user = MagicMock(id=user_id, email="a@x.com", full_name="A")
        users_result = MagicMock()
        users_result.all.return_value = [(user, "Org A")]

        old = datetime.now(UTC) - timedelta(days=cli_admin.DORMANCY_THRESHOLD_DAYS + 1)
        login_row = MagicMock(actor_id=user_id, last_login=old)
        login_result = MagicMock()
        login_result.all.return_value = [login_row]

        session.execute = AsyncMock(side_effect=[users_result, login_result])

        rows = await cli_admin._collect_admin_rows(session, organization_id=None)
        assert len(rows) == 1
        assert rows[0].dormant is True
