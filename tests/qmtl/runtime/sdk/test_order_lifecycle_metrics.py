from qmtl.foundation.common.metrics_factory import get_mapping_store
from qmtl.runtime.sdk import metrics as sdk_metrics


def test_order_lifecycle_counters_increment():
    sdk_metrics.set_world_id("test")
    # Publishing
    published_store = get_mapping_store(sdk_metrics.orders_published_total, dict)
    fills_store = get_mapping_store(sdk_metrics.fills_ingested_total, dict)
    rejected_store = get_mapping_store(sdk_metrics.orders_rejected_total, dict)

    before = published_store.get("test", 0)
    sdk_metrics.record_order_published()
    after = published_store.get("test", 0)
    assert after == before + 1

    # Fill ingest
    before = fills_store.get("test", 0)
    sdk_metrics.record_fill_ingested()
    after = fills_store.get("test", 0)
    assert after == before + 1

    # Rejection
    sdk_metrics.record_order_rejected("backpressure")
    key = ("test", "backpressure")
    assert rejected_store.get(key, 0) >= 1
