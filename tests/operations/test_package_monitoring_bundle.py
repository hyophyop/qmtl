from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.package_monitoring_bundle import Bundle, build_helm


def test_build_helm_appends_extra_dashboards(tmp_path: Path) -> None:
    dashboard_payload = {
        "uid": "base-dashboard",
        "title": "Base Dashboard",
        "panels": [],
    }
    bundle = Bundle(
        name="demo_observability",
        version=1,
        dashboards=[dashboard_payload],
        recording_rules=[],
    )

    build_helm(bundle, tmp_path)

    chart_dir = tmp_path / "helm" / bundle.name
    values = yaml.safe_load((chart_dir / "values.yaml").read_text())
    assert values["grafanaDashboards"]["extraDashboards"] == []
    assert len(values["grafanaDashboards"]["dashboards"]) == 1
    rendered_json = values["grafanaDashboards"]["dashboards"][0]["json"]
    assert json.loads(rendered_json)["uid"] == "base-dashboard"

    sample = yaml.safe_load((chart_dir / "values-sample.yaml").read_text())
    assert "dashboards" not in sample["grafanaDashboards"]
    assert sample["grafanaDashboards"]["extraDashboards"] == []

    template = (chart_dir / "templates" / "grafana-dashboards.yaml").read_text()
    assert "concat $base $extra" in template
    assert "Use extraDashboards" in (chart_dir / "values-sample.yaml").read_text()
