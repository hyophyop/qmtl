import pytest

from qmtl.worldservice.storage import Storage


@pytest.mark.asyncio
async def test_backfill_world_node_refs_recomputes_eval_keys():
    storage = Storage()
    legacy = [
        {
            "world_id": "w1",
            "node_id": "blake3:node-1",
            "status": "valid",
            "last_eval_key": "blake3:legacy",
            "annotations": {
                "contract_id": "contract-1",
                "dataset_fingerprint": "ohlcv:ASOF=2025-09-30",
                "code_version": "rev-a",
                "resource_policy": "baseline",
            },
        }
    ]

    await storage.load_legacy_world_node_refs(legacy, default_domain="dryrun")
    migrated = await storage.backfill_world_node_refs()

    assert migrated == [
        {
            "world_id": "w1",
            "node_id": "blake3:node-1",
            "execution_domain": "dryrun",
            "status": "valid",
            "last_eval_key": Storage.compute_eval_key(
                node_id="blake3:node-1",
                world_id="w1",
                execution_domain="dryrun",
                metadata=legacy[0]["annotations"],
            ),
            "annotations": legacy[0]["annotations"],
        }
    ]

    audit = await storage.get_audit("w1")
    assert any(event["event"] == "world_node_ref_migrated" and event["mode"] == "backfill" for event in audit)


@pytest.mark.asyncio
async def test_lazy_world_node_ref_upgrade_on_access():
    storage = Storage()

    def resolver(record):
        annotations = record.get("annotations") or {}
        return annotations.get("domain_hint", "live")

    legacy = [
        {
            "world_id": "w2",
            "node_id": "blake3:node-2",
            "status": "validating",
            "annotations": {
                "domain_hint": "shadow",
                "contract_id": "contract-2",
                "dataset_fingerprint": "ohlcv:ASOF=2025-09-15",
                "code_version": "rev-b",
                "resource_policy": "restricted",
            },
        }
    ]

    await storage.load_legacy_world_node_refs(legacy, domain_resolver=resolver)

    # Lazy upgrade when fetching a specific domain
    record = await storage.get_world_node_ref("w2", "blake3:node-2", "shadow")
    assert record is not None
    assert record["execution_domain"] == "shadow"
    expected_eval_key = Storage.compute_eval_key(
        node_id="blake3:node-2",
        world_id="w2",
        execution_domain="shadow",
        metadata=legacy[0]["annotations"],
    )
    assert record["last_eval_key"] == expected_eval_key

    audit = await storage.get_audit("w2")
    assert any(event["event"] == "world_node_ref_migrated" and event["mode"] == "lazy" for event in audit)

    # Listing should return the upgraded entry without duplicating it
    listing = await storage.list_world_node_refs("w2")
    assert listing == [record]
