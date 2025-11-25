from qmtl.services.dagmanager.schema_validator import SUPPORTED_VERSIONS, validate_dag


def test_validate_dag_requires_version() -> None:
    ok, version, errors = validate_dag({"nodes": []})

    assert not ok
    assert version == ""
    assert errors and errors[0]["message"].startswith("schema_version is required")


def test_validate_dag_rejects_unknown_version() -> None:
    ok, version, errors = validate_dag({"schema_version": "v9", "nodes": []})

    assert not ok
    assert version == "v9"
    assert errors and errors[0]["message"].startswith("unsupported schema version")
    assert errors[0]["supported"] == sorted(SUPPORTED_VERSIONS)


def test_validate_dag_accepts_supported_version() -> None:
    ok, version, errors = validate_dag({"schema_version": "v1", "nodes": []})

    assert ok
    assert version == "v1"
    assert errors == []
