import pytest
from qmtl.foundation.common.nodespec import CanonicalNodeSpec

def test_schema_compat_id_only():
    spec = CanonicalNodeSpec()
    spec.with_schema_compat_id("major-v2")
    assert spec.schema_compat_id == "major-v2"

def test_schema_id_only_as_fallback():
    spec = CanonicalNodeSpec()
    spec.with_schema_compat_id(None, fallback="major-v1")
    assert spec.schema_compat_id == "major-v1"

def test_both_ids_matching():
    spec = CanonicalNodeSpec()
    spec.with_schema_compat_id("major-v1", fallback="major-v1")
    assert spec.schema_compat_id == "major-v1"

def test_both_ids_conflicting_raises_error():
    spec = CanonicalNodeSpec()
    with pytest.raises(ValueError, match="must match if both are provided"):
        spec.with_schema_compat_id("major-v2", fallback="major-v1")

def test_empty_fallback_ignored():
    spec = CanonicalNodeSpec()
    spec.with_schema_compat_id("major-v1", fallback="")
    assert spec.schema_compat_id == "major-v1"

def test_empty_value_uses_fallback():
    spec = CanonicalNodeSpec()
    spec.with_schema_compat_id("", fallback="major-v1")
    assert spec.schema_compat_id == "major-v1"

def test_none_value_none_fallback():
    spec = CanonicalNodeSpec()
    spec.with_schema_compat_id(None, fallback=None)
    assert spec.schema_compat_id == ""

def test_from_payload_conflict():
    payload = {
        "schema_compat_id": "A",
        "schema_id": "B"
    }
    with pytest.raises(ValueError, match="must match if both are provided"):
        CanonicalNodeSpec.from_payload(payload)

def test_from_payload_no_conflict():
    payload = {
        "schema_compat_id": "A",
        "schema_id": "A"
    }
    spec = CanonicalNodeSpec.from_payload(payload)
    assert spec.schema_compat_id == "A"
