from __future__ import annotations

import json
from pathlib import Path

import pytest

BUNDLE_PATH = Path("operations/monitoring/seamless_v2.jsonnet")


@pytest.fixture(scope="module")
def bundle() -> dict:
    text = BUNDLE_PATH.read_text()
    data = json.loads(text)
    return data


def test_bundle_contains_expected_dashboards(bundle: dict) -> None:
    titles = {dash["title"] for dash in bundle["dashboards"]}
    assert {
        "Seamless SLA Overview",
        "Backfill Coordinator Health",
        "Conformance Quality",
    }.issubset(titles)


def test_bundle_queries_reference_metrics(bundle: dict) -> None:
    expressions = [
        target["expr"]
        for dashboard in bundle["dashboards"]
        for panel in dashboard.get("panels", [])
        for target in panel.get("targets", [])
    ]
    assert any("seamless_sla_deadline_seconds" in expr for expr in expressions)
    assert any("backfill_completion_ratio" in expr for expr in expressions)
    assert any("seamless_conformance_flag_total" in expr for expr in expressions)


def test_recording_rules_defined(bundle: dict) -> None:
    rules = bundle.get("recordingRules", [])
    assert any(rule["name"] == "seamless_sla_total_p99_seconds" for rule in rules)
