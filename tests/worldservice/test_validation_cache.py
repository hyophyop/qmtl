import httpx
import pytest

from qmtl.common.hashutils import hash_bytes
from qmtl.worldservice.api import create_app
from qmtl.worldservice.storage import Storage, ValidationCacheEntry


@pytest.mark.asyncio
async def test_validation_cache_scoped_by_execution_domain_storage():
    store = Storage()
    context = {
        "node_id": "blake3:node-1",
        "execution_domain": "backtest",
        "contract_id": "contract-a",
        "dataset_fingerprint": "lake:blake3:data-a",
        "code_version": "rev1",
        "resource_policy": "standard",
    }
    await store.set_validation_cache(
        "world-1",
        **context,
        result="valid",
        metrics={"score": 0.9},
        timestamp="2025-01-01T00:00:00Z",
    )

    cached = await store.get_validation_cache("world-1", **context)
    assert cached is not None
    assert cached.eval_key.startswith("blake3:")

    other_domain = await store.get_validation_cache(
        "world-1",
        **{**context, "execution_domain": "live"},
    )
    assert other_domain is None

    cached_again = await store.get_validation_cache("world-1", **context)
    assert cached_again is not None


@pytest.mark.asyncio
async def test_validation_cache_invalidation_on_context_change():
    store = Storage()
    context = {
        "node_id": "blake3:node-2",
        "execution_domain": "backtest",
        "contract_id": "contract-a",
        "dataset_fingerprint": "lake:blake3:data-a",
        "code_version": "rev1",
        "resource_policy": "standard",
    }
    await store.set_validation_cache(
        "world-2",
        **context,
        result="valid",
        metrics={"score": 0.9},
        timestamp="2025-01-01T00:00:00Z",
    )

    changed = await store.get_validation_cache(
        "world-2",
        **{**context, "dataset_fingerprint": "lake:blake3:data-b"},
    )
    assert changed is None

    # Cache was invalidated because context changed
    cached = await store.get_validation_cache("world-2", **context)
    assert cached is None


@pytest.mark.asyncio
async def test_validation_cache_invalidation_handles_domain_normalisation():
    store = Storage()
    context = {
        "node_id": "blake3:node-2a",
        "execution_domain": "backtest",
        "contract_id": "contract-a",
        "dataset_fingerprint": "lake:blake3:data-a",
        "code_version": "rev1",
        "resource_policy": "standard",
    }

    await store.set_validation_cache(
        "world-2a",
        **context,
        result="valid",
        metrics={"score": 0.9},
        timestamp="2025-01-01T00:00:00Z",
    )

    changed = await store.get_validation_cache(
        "world-2a",
        **{
            **context,
            "execution_domain": "BACKTEST",
            "dataset_fingerprint": "lake:blake3:data-b",
        },
    )
    assert changed is None

    cached = await store.get_validation_cache("world-2a", **context)
    assert cached is None


@pytest.mark.asyncio
async def test_validation_cache_endpoints_domain_and_context_handling():
    app = create_app()
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "world-api"})

            context = {
                "node_id": "blake3:node-3",
                "execution_domain": "backtest",
                "contract_id": "contract-a",
                "dataset_fingerprint": "lake:blake3:data-a",
                "code_version": "rev1",
                "resource_policy": "standard",
            }
            payload = {**context, "result": "valid", "metrics": {"score": 1.0}, "timestamp": "2025-01-01T00:00:00Z"}

            store_resp = await client.post("/worlds/world-api/validations/cache", json=payload)
            assert store_resp.status_code == 200
            body = store_resp.json()
            assert body["cached"] is True
            assert isinstance(body["eval_key"], str)
            assert body["eval_key"].startswith("blake3:")

            lookup_resp = await client.post("/worlds/world-api/validations/cache/lookup", json=context)
            lookup_body = lookup_resp.json()
            assert lookup_body["cached"] is True
            assert lookup_body["eval_key"] == body["eval_key"]

            other_domain_resp = await client.post(
                "/worlds/world-api/validations/cache/lookup",
                json={**context, "execution_domain": "live"},
            )
            other_domain_body = other_domain_resp.json()
            assert other_domain_body["cached"] is False

            # Domain-specific miss should not evict the original cache
            repeat_lookup = await client.post(
                "/worlds/world-api/validations/cache/lookup", json=context
            )
            assert repeat_lookup.json()["cached"] is True

            # Context change invalidates the cache entry
            mismatch_lookup = await client.post(
                "/worlds/world-api/validations/cache/lookup",
                json={**context, "dataset_fingerprint": "lake:blake3:data-b"},
            )
            assert mismatch_lookup.json()["cached"] is False

            # Original context should now miss because of invalidation
            after_invalidation = await client.post(
                "/worlds/world-api/validations/cache/lookup", json=context
            )
            assert after_invalidation.json()["cached"] is False

            # Re-store and then delete explicitly via API
            await client.post("/worlds/world-api/validations/cache", json=payload)
            delete_resp = await client.delete(
                "/worlds/world-api/validations/blake3:node-3",
                params={"execution_domain": "backtest"},
            )
            assert delete_resp.status_code == 204
            final_lookup = await client.post(
                "/worlds/world-api/validations/cache/lookup", json=context
            )
            assert final_lookup.json()["cached"] is False


@pytest.mark.asyncio
async def test_validation_cache_normalises_execution_domain_on_set():
    store = Storage()
    world_id = "world-normalised"
    context = {
        "node_id": "blake3:node-norm",
        "execution_domain": "backtest",
        "contract_id": "contract-norm",
        "dataset_fingerprint": "lake:blake3:norm",
        "code_version": "rev1",
        "resource_policy": "standard",
    }

    await store.set_validation_cache(
        world_id,
        **{**context, "execution_domain": "BackTest"},
        result="valid",
        metrics={"score": 0.7},
        timestamp="2025-02-02T00:00:00Z",
    )

    cached = await store.get_validation_cache(world_id, **context)
    assert cached is not None
    assert cached.execution_domain == "backtest"

    node_cache = store.validation_cache[world_id][context["node_id"]]
    assert "backtest" in node_cache
    assert "BackTest" not in node_cache


@pytest.mark.asyncio
async def test_validation_cache_legacy_payloads_are_normalised_and_invalidated():
    store = Storage()
    world_id = "world-legacy"
    node_id = "blake3:legacy-node"
    context = {
        "node_id": node_id,
        "execution_domain": "backtest",
        "contract_id": "contract-legacy",
        "dataset_fingerprint": "lake:blake3:legacy",
        "code_version": "rev0",
        "resource_policy": "standard",
    }

    legacy_components = [
        node_id,
        world_id,
        context["contract_id"],
        context["dataset_fingerprint"],
        context["code_version"],
        context["resource_policy"],
    ]
    legacy_payload = "\x1f".join(str(part) for part in legacy_components).encode()
    legacy_eval_key = hash_bytes(legacy_payload)

    store.validation_cache.setdefault(world_id, {})[node_id] = {
        "backtest": {
            "eval_key": legacy_eval_key,
            "node_id": node_id,
            "contract_id": context["contract_id"],
            "dataset_fingerprint": context["dataset_fingerprint"],
            "code_version": context["code_version"],
            "resource_policy": context["resource_policy"],
            "result": "valid",
            "metrics": {"score": 0.1},
            "timestamp": "2024-01-01T00:00:00Z",
        }
    }

    cached = await store.get_validation_cache(world_id, **context)
    assert cached is None
    assert world_id not in store.validation_cache

    # Seed a dict payload that already follows the new EvalKey scheme to ensure
    # lazy normalisation converts it into a ValidationCacheEntry instance.
    eval_key = store._compute_eval_key(**context, world_id=world_id)  # type: ignore[arg-type]
    store.validation_cache.setdefault(world_id, {})[node_id] = {
        "backtest": {
            "eval_key": eval_key,
            "node_id": node_id,
            "execution_domain": "backtest",
            "contract_id": context["contract_id"],
            "dataset_fingerprint": context["dataset_fingerprint"],
            "code_version": context["code_version"],
            "resource_policy": context["resource_policy"],
            "result": "valid",
            "metrics": {"score": 1.0},
            "timestamp": "2025-01-01T00:00:00Z",
        }
    }

    cached_updated = await store.get_validation_cache(world_id, **context)
    assert cached_updated is not None
    assert isinstance(cached_updated, ValidationCacheEntry)
    assert isinstance(store.validation_cache[world_id][node_id]["backtest"], ValidationCacheEntry)
