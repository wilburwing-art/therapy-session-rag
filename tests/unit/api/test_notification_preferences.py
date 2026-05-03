"""Tests for the PATCH /users/me/notifications endpoint helpers."""

import pytest

from src.api.v1.endpoints.users import (
    NotificationPreferencesUpdate,
    _merge_notification_preferences,
)


class TestMergeNotificationPreferences:
    """Unit tests for the merge helper that applies a partial update."""

    def test_empty_update_returns_top_level_copy(self) -> None:
        current = {"channels": {"sms": True}}
        merged = _merge_notification_preferences(
            current,
            NotificationPreferencesUpdate(),
        )
        assert merged == current
        # Top-level mutation doesn't leak back.
        merged["new_field"] = "x"
        assert "new_field" not in current

    def test_channels_merge_preserves_existing_keys(self) -> None:
        current = {"channels": {"sms": True, "email": True}}
        merged = _merge_notification_preferences(
            current,
            NotificationPreferencesUpdate(channels={"sms": False}),
        )
        assert merged["channels"] == {"sms": False, "email": True}

    def test_unknown_channel_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown channels"):
            _merge_notification_preferences(
                {},
                NotificationPreferencesUpdate(channels={"carrier_pigeon": True}),
            )

    def test_kinds_merge_preserves_existing(self) -> None:
        current = {"kinds": {"homework_due": True}}
        merged = _merge_notification_preferences(
            current,
            NotificationPreferencesUpdate(kinds={"session_upcoming": True}),
        )
        assert merged["kinds"] == {
            "homework_due": True,
            "session_upcoming": True,
        }

    def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown reminder kinds"):
            _merge_notification_preferences(
                {},
                NotificationPreferencesUpdate(kinds={"birthday": True}),
            )

    def test_phone_number_empty_string_clears(self) -> None:
        current = {"phone_number": "+15551234567"}
        merged = _merge_notification_preferences(
            current,
            NotificationPreferencesUpdate(phone_number=""),
        )
        assert merged["phone_number"] is None

    def test_phone_number_updates(self) -> None:
        merged = _merge_notification_preferences(
            {},
            NotificationPreferencesUpdate(phone_number="+15551234567"),
        )
        assert merged["phone_number"] == "+15551234567"

    def test_quiet_hours_and_timezone(self) -> None:
        merged = _merge_notification_preferences(
            {},
            NotificationPreferencesUpdate(
                quiet_hours_start=22,
                quiet_hours_end=7,
                timezone="America/Los_Angeles",
            ),
        )
        assert merged["quiet_hours_start"] == 22
        assert merged["quiet_hours_end"] == 7
        assert merged["timezone"] == "America/Los_Angeles"

    def test_quiet_hours_out_of_range_rejected_by_model(self) -> None:
        with pytest.raises(ValueError):
            NotificationPreferencesUpdate(quiet_hours_start=24)
        with pytest.raises(ValueError):
            NotificationPreferencesUpdate(quiet_hours_end=-1)
