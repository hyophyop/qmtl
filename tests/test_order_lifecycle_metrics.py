from qmtl.sdk import metrics as sdk_metrics


def test_order_lifecycle_counters_increment():
    sdk_metrics.set_world_id("test")
    # Publishing
    before = sdk_metrics.orders_published_total._vals.get("test", 0)  # type: ignore[attr-defined]
    sdk_metrics.record_order_published()
    after = sdk_metrics.orders_published_total._vals.get("test", 0)  # type: ignore[attr-defined]
    assert after == before + 1

    # Fill ingest
    before = sdk_metrics.fills_ingested_total._vals.get("test", 0)  # type: ignore[attr-defined]
    sdk_metrics.record_fill_ingested()
    after = sdk_metrics.fills_ingested_total._vals.get("test", 0)  # type: ignore[attr-defined]
    assert after == before + 1

    # Rejection
    sdk_metrics.record_order_rejected("backpressure")
    key = ("test", "backpressure")
    assert sdk_metrics.orders_rejected_total._vals.get(key, 0) >= 1  # type: ignore[attr-defined]
