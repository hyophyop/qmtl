from __future__ import annotations

import time
import httpx
from qmtl.sdk import metrics


def test_metrics_endpoint_exposes_backfill_gauges() -> None:
    metrics.reset_metrics()
    metrics.start_metrics_server(port=8006)
    metrics.observe_backfill_start("n", 60)
    metrics.observe_backfill_complete("n", 60, 123456)
    time.sleep(0.1)
    resp = httpx.get("http://localhost:8006/metrics")
    text = resp.text
    assert "backfill_jobs_in_progress" in text
    assert 'backfill_last_timestamp{interval="60",node_id="n"}' in text
