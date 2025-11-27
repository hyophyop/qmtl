"""Tests for qmtl.integrations.sr.adapters.generic module."""

from qmtl.integrations.sr.adapters.generic import (
    GenericCandidate,
    GenericSRAdapter,
)
from qmtl.integrations.sr.types import SRCandidate


class TestGenericCandidate:
    """Tests for GenericCandidate."""

    def test_create_minimal(self):
        """Test creating with minimal args."""
        candidate = GenericCandidate(expression="x + y")
        assert candidate.expression == "x + y"
        assert candidate.source_engine == "generic"
        assert candidate.raw_data == {}

    def test_create_full(self):
        """Test creating with all args."""
        candidate = GenericCandidate(
            expression="x * y",
            metadata={"id": "test_001"},
            fitness=0.9,
            complexity=2.0,
            generation=5,
            source_engine="my_automl",
            raw_data={"original": "data"},
        )
        assert candidate.expression == "x * y"
        assert candidate.source_engine == "my_automl"
        assert candidate.raw_data == {"original": "data"}
        assert candidate.fitness == 0.9

    def test_get_id_from_metadata(self):
        """Test get_id returns metadata id when present."""
        candidate = GenericCandidate(
            expression="x + y",
            metadata={"id": "custom_id"},
        )
        assert candidate.get_id() == "custom_id"

    def test_get_id_auto_generated(self):
        """Test get_id auto-generates from engine name."""
        candidate = GenericCandidate(
            expression="x + y",
            source_engine="test_engine",
            generation=5,
        )
        id_ = candidate.get_id()
        assert "test_engine" in id_
        assert "5" in id_

    def test_protocol_compliance(self):
        """Test GenericCandidate complies with SRCandidate protocol."""
        candidate = GenericCandidate(expression="x + y")
        assert isinstance(candidate, SRCandidate)


class TestGenericSRAdapter:
    """Tests for GenericSRAdapter."""

    def test_init_defaults(self):
        """Test initialization with defaults."""
        adapter = GenericSRAdapter()
        assert adapter.engine_name == "generic"
        assert adapter.default_fitness == 0.0
        assert adapter.default_complexity == 0.0

    def test_init_custom(self):
        """Test initialization with custom values."""
        adapter = GenericSRAdapter(
            engine_name="my_engine",
            default_fitness=0.5,
            default_complexity=1.0,
        )
        assert adapter.engine_name == "my_engine"
        assert adapter.default_fitness == 0.5
        assert adapter.default_complexity == 1.0

    def test_from_expression(self):
        """Test creating candidate from expression."""
        adapter = GenericSRAdapter(engine_name="test")
        candidate = adapter.from_expression(
            "x + y",
            fitness=0.8,
            complexity=2.0,
            generation=10,
        )

        assert candidate.expression == "x + y"
        assert candidate.fitness == 0.8
        assert candidate.complexity == 2.0
        assert candidate.generation == 10
        assert candidate.source_engine == "test"

    def test_from_expression_defaults(self):
        """Test from_expression uses adapter defaults."""
        adapter = GenericSRAdapter(
            default_fitness=0.5,
            default_complexity=1.0,
        )
        candidate = adapter.from_expression("x + y")

        assert candidate.fitness == 0.5
        assert candidate.complexity == 1.0

    def test_from_dict(self):
        """Test creating candidate from dict."""
        adapter = GenericSRAdapter()
        data = {
            "expression": "x * y",
            "fitness": 0.9,
            "complexity": 3.0,
            "generation": 5,
            "extra_field": "value",
        }
        candidate = adapter.from_dict(data)

        assert candidate.expression == "x * y"
        assert candidate.fitness == 0.9
        assert candidate.complexity == 3.0
        assert candidate.generation == 5
        assert candidate.metadata["extra_field"] == "value"

    def test_from_dict_custom_keys(self):
        """Test from_dict with custom key names."""
        adapter = GenericSRAdapter()
        data = {
            "expr": "x + y",
            "score": 0.8,
            "comp": 2.0,
            "gen": 10,
            "id": "custom_001",
        }
        candidate = adapter.from_dict(
            data,
            expression_key="expr",
            fitness_key="score",
            complexity_key="comp",
            generation_key="gen",
            id_key="id",
        )

        assert candidate.expression == "x + y"
        assert candidate.fitness == 0.8
        assert candidate.complexity == 2.0
        assert candidate.generation == 10
        assert candidate.metadata["id"] == "custom_001"

    def test_from_dict_list(self):
        """Test creating multiple candidates from dict list."""
        adapter = GenericSRAdapter()
        data_list = [
            {"expression": "x + y", "fitness": 0.8},
            {"expression": "x * y", "fitness": 0.9},
            {"expression": "x - y", "fitness": 0.7},
        ]
        candidates = adapter.from_dict_list(data_list)

        assert len(candidates) == 3
        assert candidates[0].expression == "x + y"
        assert candidates[1].expression == "x * y"
        assert candidates[2].expression == "x - y"

    def test_from_tuples(self):
        """Test creating candidates from tuples."""
        adapter = GenericSRAdapter()
        tuples = [
            ("x + y", 0.8),
            ("x * y", 0.9),
            ("x - y", 0.7),
        ]
        candidates = adapter.from_tuples(tuples, generation=5)

        assert len(candidates) == 3
        assert candidates[0].expression == "x + y"
        assert candidates[0].fitness == 0.8
        assert candidates[0].generation == 5

    def test_from_custom(self):
        """Test creating candidates with custom extractor."""
        adapter = GenericSRAdapter()

        # Simulate custom objects from an SR engine
        class FakeIndividual:
            def __init__(self, expr, score):
                self.expr = expr
                self.score = score

        items = [
            FakeIndividual("x + y", 0.8),
            FakeIndividual("x * y", 0.9),
        ]

        def extractor(item):
            return {
                "expression": item.expr,
                "fitness": item.score,
                "generation": 0,
            }

        candidates = adapter.from_custom(items, extractor)

        assert len(candidates) == 2
        assert candidates[0].expression == "x + y"
        assert candidates[0].fitness == 0.8
        assert candidates[1].expression == "x * y"
        assert candidates[1].fitness == 0.9
