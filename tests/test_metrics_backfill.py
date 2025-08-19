import time
import urllib.request

from prometheus_client import start_http_server

from qmtl.sdk import metrics


def test_metrics_server_reports_backfill_gauges() -> None:
    """Start a metrics HTTP server and ensure backfill gauges are exposed."""
    metrics.reset_metrics()
    server, _ = start_http_server(0)
    port = server.server_port
    try:
        # Give the background server thread a moment to start
        time.sleep(0.05)
        metrics.observe_backfill_start("node", 60)
        metrics.observe_backfill_complete("node", 60, 123)
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics").read().decode()
        assert "backfill_jobs_in_progress 0" in resp
        assert 'backfill_last_timestamp{interval="60",node_id="node"} 123' in resp
    finally:
        server.shutdown()
        server.server_close()
