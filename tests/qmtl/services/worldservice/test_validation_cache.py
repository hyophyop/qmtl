import httpx
import pytest

from qmtl.foundation.common.hashutils import hash_bytes
from qmtl.services.worldservice.api import create_app
from qmtl.services.worldservice.storage import Storage, ValidationCacheEntry


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
        **{**context, "execution_domain": "dryrun"},
    )
    assert other_domain is None

    cached_again = await store.get_validation_cache("world-1", **context)
    assert cached_again is not None


@pytest.mark.asyncio
async def test_validation_cache_accepts_execution_domain_aliases_via_api():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "world-alias"})

            payload = {
                "node_id": "blake3:alias-node",
                "execution_domain": "paper",
                "contract_id": "contract-alias",
                "dataset_fingerprint": "lake:blake3:alias",
                "code_version": "rev0",
                "resource_policy": "standard",
                "result": "valid",
                "metrics": {"score": 0.42},
            }

            resp = await client.post("/worlds/world-alias/validations/cache", json=payload)
            assert resp.status_code == 200
            assert resp.json()["cached"] is True

            lookup = await client.post(
                "/worlds/world-alias/validations/cache/lookup",
                json={key: payload[key] for key in payload if key not in {"result", "metrics"}},
            )
            assert lookup.status_code == 200
            body = lookup.json()
            assert body["cached"] is True
            assert body["result"] == "valid"
            assert body["metrics"] == {"score": 0.42}


@pytest.mark.asyncio
async def test_validation_cache_rejects_unknown_execution_domain_via_api():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "world-invalid"})

            payload = {
                "node_id": "blake3:alias-node",
                "execution_domain": "invalid-mode",
                "contract_id": "contract-invalid",
                "dataset_fingerprint": "lake:blake3:alias",
                "code_version": "rev0",
                "resource_policy": "standard",
                "result": "valid",
                "metrics": {"score": 0.42},
            }

            resp = await client.post("/worlds/world-invalid/validations/cache", json=payload)
            assert resp.status_code == 422
            assert "unknown execution_domain" in resp.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context_update",
    [
        {"dataset_fingerprint": "lake:blake3:data-b"},
        {"code_version": "rev2"},
        {"resource_policy": "premium"},
        {"contract_id": "contract-b"},
    ],
)
async def test_validation_cache_invalidation_on_context_change(context_update):
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
        **{**context, **context_update},
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
    app = create_app(storage=Storage())
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
                json={**context, "execution_domain": "dryrun"},
            )
            other_domain_body = other_domain_resp.json()
            assert other_domain_body["cached"] is False

            # Domain-specific miss should not evict the original cache
            repeat_lookup = await client.post(
                "/worlds/world-api/validations/cache/lookup", json=context
            )
            assert repeat_lookup.json()["cached"] is True

            # Context change invalidates the cache entry
            def base_payload() -> dict:
                return {
                    **context,
                    "result": "valid",
                    "metrics": {"score": 1.0},
                    "timestamp": "2025-01-01T00:00:00Z",
                }

            invalidation_cases = [
                {"dataset_fingerprint": "lake:blake3:data-b"},
                {"code_version": "rev2"},
                {"resource_policy": "premium"},
                {"contract_id": "contract-b"},
            ]

            for mutation in invalidation_cases:
                store_resp = await client.post(
                    "/worlds/world-api/validations/cache", json=base_payload()
                )
                assert store_resp.status_code == 200
                assert store_resp.json()["cached"] is True

                lookup_resp = await client.post(
                    "/worlds/world-api/validations/cache/lookup", json=context
                )
                assert lookup_resp.json()["cached"] is True

                mismatch_lookup = await client.post(
                    "/worlds/world-api/validations/cache/lookup",
                    json={**context, **mutation},
                )
                assert mismatch_lookup.json()["cached"] is False

                # Original context should now miss because of invalidation
                after_invalidation = await client.post(
                    "/worlds/world-api/validations/cache/lookup", json=context
                )
                assert after_invalidation.json()["cached"] is False

            # Re-store and then delete explicitly via API
            await client.post(
                "/worlds/world-api/validations/cache", json=base_payload()
            )
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

    node_cache = store._validation_cache.cache[world_id][context["node_id"]]
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

    store._validation_cache.cache.setdefault(world_id, {})[node_id] = {
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
    assert world_id not in store._validation_cache.cache

    audit_repo = store._validation_cache.audit  # type: ignore[attr-defined]
    audit_entries = audit_repo.list_entries(world_id)  # type: ignore[attr-defined]
    normalized_events = [event for event in audit_entries if event["event"] == "validation_cache_bucket_normalized"]
    assert normalized_events
    assert any("backtest" in event.get("domains", []) for event in normalized_events)

    invalidated_events = [event for event in audit_entries if event["event"] == "validation_cache_invalidated"]
    assert invalidated_events
    assert invalidated_events[-1]["reason"] == "context_mismatch"

    # Seed a dict payload that already follows the new EvalKey scheme to ensure
    # lazy normalisation converts it into a ValidationCacheEntry instance.
    eval_key = store._validation_cache._compute_eval_key(**context, world_id=world_id)  # type: ignore[arg-type]
    store._validation_cache.cache.setdefault(world_id, {})[node_id] = {
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
    assert isinstance(store._validation_cache.cache[world_id][node_id]["backtest"], ValidationCacheEntry)
