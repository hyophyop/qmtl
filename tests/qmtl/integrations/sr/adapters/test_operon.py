"""Tests for qmtl.integrations.sr.adapters.operon module."""

from qmtl.integrations.sr.adapters.operon import (
    OperonCandidate,
    is_pyoperon_available,
)
from qmtl.integrations.sr.types import SRCandidate


class TestOperonCandidate:
    """Tests for OperonCandidate."""

    def test_create_minimal(self):
        """Test creating with minimal args."""
        candidate = OperonCandidate(expression="x + y")
        assert candidate.expression == "x + y"
        assert candidate.tree_depth == 0
        assert candidate.num_nodes == 0
        assert candidate.r2_score == 0.0
        assert candidate.nmse == 0.0

    def test_create_full(self):
        """Test creating with all args."""
        candidate = OperonCandidate(
            expression="Add(x, Mul(y, 2))",
            metadata={"id": "op_001"},
            fitness=0.95,
            complexity=4.0,
            generation=20,
            tree_depth=3,
            num_nodes=5,
            r2_score=0.92,
            nmse=0.08,
        )
        assert candidate.expression == "Add(x, Mul(y, 2))"
        assert candidate.tree_depth == 3
        assert candidate.num_nodes == 5
        assert candidate.r2_score == 0.92
        assert candidate.nmse == 0.08
        assert candidate.fitness == 0.95

    def test_get_id_from_metadata(self):
        """Test get_id returns metadata id when present."""
        candidate = OperonCandidate(
            expression="x + y",
            metadata={"id": "custom_op_id"},
        )
        assert candidate.get_id() == "custom_op_id"

    def test_get_id_auto_generated(self):
        """Test get_id auto-generates with operon prefix."""
        candidate = OperonCandidate(
            expression="x + y",
            generation=10,
        )
        id_ = candidate.get_id()
        assert id_.startswith("operon_")
        assert "10" in id_

    def test_protocol_compliance(self):
        """Test OperonCandidate complies with SRCandidate protocol."""
        candidate = OperonCandidate(expression="x + y")
        assert isinstance(candidate, SRCandidate)


class TestIsPyoperonAvailable:
    """Tests for is_pyoperon_available function."""

    def test_returns_bool(self):
        """Test that function returns a boolean."""
        result = is_pyoperon_available()
        assert isinstance(result, bool)


class TestOperonAdapterWithoutPyoperon:
    """Tests for OperonAdapter when pyoperon is not installed."""

    def test_import_error_without_pyoperon(self):
        """Test that OperonAdapter raises ImportError without pyoperon."""
        if is_pyoperon_available():
            # Skip this test if pyoperon is actually installed
            return

        from qmtl.integrations.sr.adapters.operon import OperonAdapter

        try:
            OperonAdapter()
            assert False, "Should raise ImportError"
        except ImportError as e:
            assert "pyoperon" in str(e)
