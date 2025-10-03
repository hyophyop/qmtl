import json

import pytest

from qmtl.foundation.common.metrics_factory import reset_metrics
from qmtl.foundation.schema import (
    SchemaRegistryClient,
    SchemaValidationError,
    SchemaValidationMode,
)
from qmtl.foundation.schema.registry import _VALIDATION_FAILURES


def test_register_and_latest():
    reg = SchemaRegistryClient()
    s1 = reg.register("prices", json.dumps({"a": 1}))
    assert s1.id > 0 and s1.version == 1
    assert reg.latest("prices").id == s1.id


def test_canary_mode_allows_incompatible_and_emits_metric():
    reset_metrics(["seamless_schema_validation_failures_total"])
    reg = SchemaRegistryClient(validation_mode=SchemaValidationMode.CANARY)
    reg.register("prices", json.dumps({"a": 1, "b": 2}))
    reg.register("prices", json.dumps({"a": 1}))

    report = reg.last_validation("prices")
    assert report is not None
    assert not report.compatible
    assert "b" in report.breaking_changes

    metric = _VALIDATION_FAILURES.labels(subject="prices", mode="canary")
    assert metric._value.get() == 1  # type: ignore[attr-defined]


def test_strict_mode_blocks_incompatible_change():
    reset_metrics(["seamless_schema_validation_failures_total"])
    reg = SchemaRegistryClient(validation_mode=SchemaValidationMode.STRICT)
    reg.register("prices", json.dumps({"a": 1, "nested": {"b": 2}}))

    with pytest.raises(SchemaValidationError):
        reg.register("prices", json.dumps({"a": 1, "nested": {}}))

    report = reg.last_validation("prices")
    assert report is not None
    assert not report.compatible
    assert any(path.endswith("nested.b") for path in report.breaking_changes)

