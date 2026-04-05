"""Unit tests for the notification type registry."""

from app.logic.notifications.registry import (
    ALL_NOTIFICATION_TYPES,
    BOOKING_CONFIRMED,
    BOOKING_REMINDER,
    USER_REGISTERED,
    NotificationTypeDef,
)


class TestNotificationTypeDef:
    """Test suite for NotificationTypeDef dataclass."""

    def test_to_dict_with_defaults(self):
        """Test converting a NotificationTypeDef with defaults to dict."""
        typedef = NotificationTypeDef(
            code="test.code",
            name="Test",
            description="Test description",
            category="test",
        )
        d = typedef.to_dict()

        assert d["code"] == "test.code"
        assert d["is_admin_only"] is False
        assert d["default_channels"] == ["email"]
        assert d["is_user_configurable"] is True

    def test_to_dict_with_custom_channels(self):
        """Test converting a NotificationTypeDef with custom channels."""
        typedef = NotificationTypeDef(
            code="test.push",
            name="Push Test",
            description="Test",
            category="test",
            default_channels=["push", "email"],
        )
        d = typedef.to_dict()

        assert d["default_channels"] == ["push", "email"]

    def test_to_dict_admin_only(self):
        """Test converting an admin-only NotificationTypeDef."""
        typedef = NotificationTypeDef(
            code="admin.alert",
            name="Admin Alert",
            description="Admin only",
            category="admin",
            is_admin_only=True,
            is_user_configurable=False,
        )
        d = typedef.to_dict()

        assert d["is_admin_only"] is True
        assert d["is_user_configurable"] is False


class TestRegistry:
    """Test the global notification types registry."""

    def test_all_types_have_unique_codes(self):
        """Verify all notification types have unique codes."""
        codes = [t.code for t in ALL_NOTIFICATION_TYPES]
        assert len(codes) == len(set(codes))

    def test_all_types_have_required_fields(self):
        """Verify all notification types have required fields."""
        for t in ALL_NOTIFICATION_TYPES:
            assert t.code
            assert t.name
            assert t.description
            assert t.category

    def test_booking_confirmed_channels(self):
        """Verify BOOKING_CONFIRMED has expected channels."""
        assert BOOKING_CONFIRMED.default_channels == ["email", "push"]
        assert BOOKING_CONFIRMED.category == "booking"

    def test_booking_reminder_not_user_configurable(self):
        """Verify BOOKING_REMINDER is not user-configurable."""
        assert BOOKING_REMINDER.is_user_configurable is False

    def test_user_registered_is_admin_only(self):
        """Verify USER_REGISTERED is admin-only."""
        assert USER_REGISTERED.is_admin_only is True

    def test_registry_has_expected_categories(self):
        """Verify the registry covers expected categories."""
        categories = {t.category for t in ALL_NOTIFICATION_TYPES}
        assert "booking" in categories
        assert "slot" in categories
        assert "event" in categories
        assert "admin" in categories
        assert "user" in categories
