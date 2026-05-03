"""Tests for the reminder scheduler lifecycle hooks."""

from unittest.mock import MagicMock, patch

from src.core.config import Settings
from src.workers.reminder_scheduler import (
    reminder_tick,
    start_scheduler,
    stop_scheduler,
)


def _settings(reminders_enabled: bool = False) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://user:pw@localhost:5432/db",  # type: ignore[arg-type]
        redis_url="redis://localhost:6379/0",  # type: ignore[arg-type]
        reminders_enabled=reminders_enabled,
    )


class TestStartSchedulerDisabled:
    def test_returns_false_when_reminders_disabled(self) -> None:
        assert start_scheduler(_settings(reminders_enabled=False)) is False

    def test_stop_noop_when_reminders_disabled(self) -> None:
        # Should not raise and should not touch Redis.
        stop_scheduler(_settings(reminders_enabled=False))


class TestStartSchedulerEnabled:
    def test_registers_recurring_tick(self) -> None:
        settings = _settings(reminders_enabled=True)
        fake_scheduler = MagicMock()
        fake_scheduler.get_jobs.return_value = []

        with (
            patch(
                "src.workers.reminder_scheduler._redis",
                return_value=MagicMock(),
            ),
            patch(
                "rq_scheduler.Scheduler",
                return_value=fake_scheduler,
            ) as mock_scheduler_cls,
        ):
            ok = start_scheduler(settings)
            assert ok is True
            mock_scheduler_cls.assert_called_once()
            fake_scheduler.schedule.assert_called_once()
            kwargs = fake_scheduler.schedule.call_args.kwargs
            assert kwargs["func"] == "src.workers.reminder_scheduler.reminder_tick"
            assert kwargs["id"] == "reminders.tick"
            assert kwargs["interval"] == settings.reminders_scheduler_interval_seconds

    def test_cancels_prior_tick_before_scheduling(self) -> None:
        settings = _settings(reminders_enabled=True)
        prior = MagicMock()
        prior.id = "reminders.tick"
        unrelated = MagicMock()
        unrelated.id = "something.else"
        fake_scheduler = MagicMock()
        fake_scheduler.get_jobs.return_value = [prior, unrelated]

        with (
            patch(
                "src.workers.reminder_scheduler._redis",
                return_value=MagicMock(),
            ),
            patch("rq_scheduler.Scheduler", return_value=fake_scheduler),
        ):
            start_scheduler(settings)
            fake_scheduler.cancel.assert_called_once_with(prior)


class TestReminderTick:
    def test_returns_noop_status(self) -> None:
        result = reminder_tick()
        assert result["status"] == "noop"
        assert "tick_id" in result


class TestStopSchedulerEnabled:
    def test_cancels_recurring_tick(self) -> None:
        settings = _settings(reminders_enabled=True)
        prior = MagicMock()
        prior.id = "reminders.tick"
        fake_scheduler = MagicMock()
        fake_scheduler.get_jobs.return_value = [prior]

        with (
            patch(
                "src.workers.reminder_scheduler._redis",
                return_value=MagicMock(),
            ),
            patch("rq_scheduler.Scheduler", return_value=fake_scheduler),
        ):
            stop_scheduler(settings)
            fake_scheduler.cancel.assert_called_once_with(prior)
