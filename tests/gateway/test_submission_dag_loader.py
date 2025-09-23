from __future__ import annotations

import base64
import json

import pytest
from fastapi import HTTPException

from qmtl.services.gateway.submission.dag_loader import DagLoader


def test_decode_accepts_base64_payload() -> None:
    dag = {"nodes": [], "meta": {}}
    encoded = base64.b64encode(json.dumps(dag).encode()).decode()

    loader = DagLoader()
    loaded = loader.decode(encoded)

    assert loaded.dag == dag


def test_load_validates_schema(monkeypatch) -> None:
    dag = {"nodes": [], "meta": {}}
    loader = DagLoader()

    calls: list[dict] = []

    def fake_validate(data):  # type: ignore[compatible-type]
        calls.append(data)
        return True, "v1", []

    monkeypatch.setattr(
        "qmtl.services.dagmanager.schema_validator.validate_dag",
        fake_validate,
    )

    loaded = loader.load(json.dumps(dag))
    assert calls and calls[0] == dag
    assert loaded.dag == dag


def test_load_raises_on_invalid_schema(monkeypatch) -> None:
    loader = DagLoader()

    def fake_validate(_dag):  # type: ignore[compatible-type]
        return False, "v1", ["broken"]

    monkeypatch.setattr(
        "qmtl.services.dagmanager.schema_validator.validate_dag",
        fake_validate,
    )

    with pytest.raises(HTTPException) as exc:
        loader.load("{}")

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "E_SCHEMA_INVALID"
