"""Tests for qmtl.integrations.sr.pysr_adapter module."""

from pathlib import Path

from qmtl.integrations.sr.pysr_adapter import (
    load_pysr_hof_as_dags,
    _load_rows,
    _latest_hof,
    REQUIRED_COLS,
)
from qmtl.integrations.sr.dag import ExpressionDagSpec


class TestLoadRows:
    """Tests for _load_rows function."""

    def test_load_valid_csv(self, tmp_path: Path):
        """Test loading a valid HOF CSV."""
        hof_path = tmp_path / "hall_of_fame.csv"
        hof_path.write_text(
            "Complexity,Loss,Equation\n"
            "1,0.5,x\n"
            "3,0.1,x + y\n"
        )

        rows = _load_rows(hof_path)

        assert len(rows) == 2
        assert rows[0]["Complexity"] == "1"
        assert rows[0]["Loss"] == "0.5"
        assert rows[0]["Equation"] == "x"

    def test_load_missing_columns(self, tmp_path: Path):
        """Test loading CSV with missing required columns."""
        hof_path = tmp_path / "hall_of_fame.csv"
        hof_path.write_text("Complexity,Loss\n1,0.5\n")

        try:
            _load_rows(hof_path)
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "missing columns" in str(e).lower()


class TestLatestHof:
    """Tests for _latest_hof function."""

    def test_find_latest(self, tmp_path: Path):
        """Test finding the latest HOF file."""
        # Create multiple run directories
        (tmp_path / "run_001").mkdir()
        (tmp_path / "run_002").mkdir()
        (tmp_path / "run_003").mkdir()

        (tmp_path / "run_001" / "hall_of_fame.csv").write_text("Complexity,Loss,Equation\n")
        (tmp_path / "run_003" / "hall_of_fame.csv").write_text("Complexity,Loss,Equation\n")

        result = _latest_hof(tmp_path)

        # Should return run_003 (latest alphabetically/numerically)
        assert "run_003" in str(result)

    def test_no_hof_found(self, tmp_path: Path):
        """Test when no HOF file exists."""
        try:
            _latest_hof(tmp_path)
            assert False, "Should raise FileNotFoundError"
        except FileNotFoundError as e:
            assert "No hall_of_fame.csv" in str(e)


class TestLoadPysrHofAsDags:
    """Tests for load_pysr_hof_as_dags function."""

    def test_load_simple_expressions(self, tmp_path: Path):
        """Test loading simple expressions."""
        hof_path = tmp_path / "hall_of_fame.csv"
        hof_path.write_text(
            "Complexity,Loss,Equation\n"
            "1,0.5,x0\n"
            "3,0.1,x0 + x1\n"
        )

        specs = load_pysr_hof_as_dags(hof_path=hof_path)

        assert len(specs) == 2
        assert all(isinstance(s, ExpressionDagSpec) for s in specs)

    def test_filter_by_max_nodes(self, tmp_path: Path):
        """Test filtering by max_nodes."""
        hof_path = tmp_path / "hall_of_fame.csv"
        hof_path.write_text(
            "Complexity,Loss,Equation\n"
            "1,0.5,x0\n"
            "10,0.01,x0 + x1 + x2 + x3 + x4 + x5 + x6 + x7 + x8 + x9\n"
        )

        specs = load_pysr_hof_as_dags(hof_path=hof_path, max_nodes=5)

        # Only the simple expression should pass
        assert len(specs) == 1
        assert specs[0].equation == "x0"

    def test_skip_unparseable(self, tmp_path: Path):
        """Test that unparseable expressions are skipped."""
        hof_path = tmp_path / "hall_of_fame.csv"
        hof_path.write_text(
            "Complexity,Loss,Equation\n"
            "1,0.5,x0\n"
            "3,0.1,((())\n"  # Unbalanced parentheses - actually invalid
        )

        specs = load_pysr_hof_as_dags(hof_path=hof_path)

        # Should only have the valid expression
        assert len(specs) == 1
        assert specs[0].equation == "x0"

    def test_expression_key_unique(self, tmp_path: Path):
        """Test that each spec gets a unique expression_key."""
        hof_path = tmp_path / "hall_of_fame.csv"
        hof_path.write_text(
            "Complexity,Loss,Equation\n"
            "1,0.5,x0\n"
            "3,0.1,x0 + x1\n"
            "5,0.05,x0 * x1\n"
        )

        specs = load_pysr_hof_as_dags(hof_path=hof_path)

        keys = [s.expression_key for s in specs]
        assert len(keys) == len(set(keys))  # All unique

    def test_preserves_metadata(self, tmp_path: Path):
        """Test that complexity and loss are preserved."""
        hof_path = tmp_path / "hall_of_fame.csv"
        hof_path.write_text(
            "Complexity,Loss,Equation\n"
            "7,0.123,x0 + x1\n"
        )

        specs = load_pysr_hof_as_dags(hof_path=hof_path)

        assert len(specs) == 1
        assert specs[0].complexity == 7
        assert specs[0].loss == 0.123

    def test_auto_find_latest(self, tmp_path: Path):
        """Test auto-finding latest HOF when path not specified."""
        # Create outputs structure
        run_dir = tmp_path / "outputs" / "run_001"
        run_dir.mkdir(parents=True)
        hof_path = run_dir / "hall_of_fame.csv"
        hof_path.write_text(
            "Complexity,Loss,Equation\n"
            "1,0.5,x0\n"
        )

        specs = load_pysr_hof_as_dags(
            hof_path=None,
            outputs_base=tmp_path / "outputs",
        )

        assert len(specs) == 1


class TestRequiredCols:
    """Tests for REQUIRED_COLS constant."""

    def test_required_cols_defined(self):
        """Test that required columns are defined."""
        assert "Equation" in REQUIRED_COLS
        assert "Complexity" in REQUIRED_COLS
        assert "Loss" in REQUIRED_COLS
