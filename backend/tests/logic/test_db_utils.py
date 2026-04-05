"""Unit tests for db_utils helper functions."""

from app.logic.utils.db_utils import get_comparison
from app.models.user import User


class TestGetComparison:
    """Test suite for get_comparison helper."""

    def test_eq_comparison(self):
        """Test equality comparison."""
        expr = get_comparison(User.name, "Alice")  # type: ignore[reportArgumentType]
        # Verify it produces a valid SQL expression
        assert str(expr.compile(compile_kwargs={"literal_binds": True}))

    def test_ne_comparison(self):
        """Test not-equal comparison."""
        expr = get_comparison(User.name, "Alice", is_not=True)  # type: ignore[reportArgumentType]
        compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
        assert "!=" in compiled or "<>" in compiled

    def test_is_none(self):
        """Test IS NULL comparison."""
        expr = get_comparison(User.name, None)  # type: ignore[reportArgumentType]
        compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
        assert "IS" in compiled.upper()

    def test_is_not_none(self):
        """Test IS NOT NULL comparison."""
        expr = get_comparison(User.name, None, is_not=True)  # type: ignore[reportArgumentType]
        compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
        assert "IS NOT" in compiled.upper()

    def test_gt_comparison(self):
        """Test greater-than comparison."""
        expr = get_comparison(User.created_at, "2026-01-01", greater_then_comp="gt")  # type: ignore[reportArgumentType]
        compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
        assert ">" in compiled

    def test_le_comparison(self):
        """Test less-than-or-equal comparison."""
        expr = get_comparison(User.created_at, "2026-01-01", greater_then_comp="le")  # type: ignore[reportArgumentType]
        compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
        assert "<=" in compiled

    def test_gt_inverted(self):
        """Test inverted greater-than becomes less-than-or-equal."""
        expr = get_comparison(
            User.created_at,
            "2026-01-01",
            is_not=True,
            greater_then_comp="gt",  # type: ignore[reportArgumentType]
        )
        compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
        assert "<=" in compiled

    def test_le_inverted(self):
        """Test inverted less-than-or-equal becomes greater-than."""
        expr = get_comparison(
            User.created_at,
            "2026-01-01",
            is_not=True,
            greater_then_comp="le",  # type: ignore[reportArgumentType]
        )
        compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
        assert ">" in compiled
