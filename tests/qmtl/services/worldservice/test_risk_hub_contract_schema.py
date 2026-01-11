import json
from pathlib import Path

import jsonschema
from referencing import Registry, Resource

from qmtl.services.risk_hub_contract import normalize_and_validate_snapshot


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _load_schema(locale: str, name: str) -> dict:
    schema_path = _repo_root() / "docs" / locale / "reference" / "schemas" / name
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _validate_with_store(schema: dict, payload: dict, store: dict) -> None:
    registry = Registry().with_resources(
        (uri, Resource.from_contents(resource_schema)) for uri, resource_schema in store.items()
    )
    jsonschema.Draft202012Validator(schema, registry=registry).validate(payload)


def test_risk_snapshot_schema_and_normalization_contract() -> None:
    snapshot = {
        "world_id": "world-1",
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"AAPL": 0.6, "MSFT": 0.4},
        "provenance": {"actor": "gateway", "stage": "paper"},
        "ttl_sec": 900,
        "realized_returns": {"strategy-a": [0.01, -0.02]},
        "stress_ref": "s3://risk-hub/stress.json",
    }
    normalized = normalize_and_validate_snapshot(
        "world-1",
        snapshot,
        actor="gateway",
        stage="paper",
    )

    for locale in ("ko", "en"):
        snapshot_schema = _load_schema(locale, "portfolio_snapshot.schema.json")
        _validate_with_store(snapshot_schema, normalized, store={snapshot_schema["$id"]: snapshot_schema})

        event_schema = _load_schema(locale, "event_risk_snapshot_updated.schema.json")
        event_payload = {
            "specversion": "1.0",
            "id": "evt-1",
            "source": "qmtl.services.worldservice",
            "type": "risk_snapshot_updated",
            "time": "2025-01-01T00:00:00Z",
            "datacontenttype": "application/json",
            "correlation_id": "risk_snapshot:world-1:abc",
            "data": {
                **normalized,
                "event_version": 1,
                "idempotency_key": f"risk_snapshot_updated:world-1:{normalized['hash']}:1",
            },
        }
        store = {
            snapshot_schema["$id"]: snapshot_schema,
            event_schema["$id"]: event_schema,
        }
        _validate_with_store(event_schema, event_payload, store=store)


def test_exit_signal_emitted_schema_contract() -> None:
    event_payload = {
        "specversion": "1.0",
        "id": "evt-2",
        "source": "qmtl.services.exit_engine",
        "type": "exit_signal_emitted",
        "time": "2025-01-01T00:00:00Z",
        "datacontenttype": "application/json",
        "correlation_id": "exit_signal:world-1:v1",
        "data": {
            "world_id": "world-1",
            "as_of": "2025-01-01T00:00:00Z",
            "snapshot_version": "v1",
            "event_version": 1,
            "idempotency_key": "exit_signal_emitted:world-1:v1:1",
            "signals": [
                {
                    "strategy_id": "strategy-1",
                    "action": "exit",
                    "reduction_ratio": 1.0,
                    "reason": "risk-limit",
                    "metrics": {"drawdown": 0.12},
                    "tags": ["priority", "systemic"],
                }
            ],
            "provenance": {"actor": "exit-engine", "stage": "paper"},
        },
    }

    for locale in ("ko", "en"):
        event_schema = _load_schema(locale, "event_exit_signal_emitted.schema.json")
        store = {event_schema["$id"]: event_schema}
        _validate_with_store(event_schema, event_payload, store=store)
