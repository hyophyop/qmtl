from __future__ import annotations

from typing import Any, Callable, cast

import pytest
from fastapi import HTTPException

from qmtl.foundation.common import crc32_of_list
from qmtl.foundation.common.compute_context import DowngradeReason
from qmtl.services.gateway import metrics
from qmtl.services.gateway.strategy_submission import (
    StrategySubmissionConfig,
    StrategySubmissionHelper,
)
from qmtl.services.gateway.submission.context_service import StrategyComputeContext

from tests.qmtl.services.gateway.helpers import build_strategy_payload
from tests.qmtl.services.gateway.fixtures import (
    DummyDagManager,
    DummyDatabase,
    DummyManager,
)


pytestmark = pytest.mark.asyncio
pytest_plugins = ("tests.qmtl.services.gateway.conftest",)


def assert_submission_result(
    result,
    *,
    expected_strategy_id: str,
    expected_sentinel: str,
    queue_map_assert: Callable[[dict], None] | None = None,
    expected_queue_map: dict | None = None,
    downgraded: bool = False,
    downgrade_reason=None,
    safe_mode: bool = False,
    queue_map_source: str | None = None,
    diff_error: bool | None = None,
    crc_fallback: bool | None = None,
):
    """Common assertions for :class:`StrategySubmissionResult` instances."""

    _assert_required_fields(result, expected_strategy_id, expected_sentinel)
    _assert_queue_map(result, expected_queue_map, queue_map_assert)
    _assert_flags(
        result,
        downgraded=downgraded,
        safe_mode=safe_mode,
        downgrade_reason=downgrade_reason,
        queue_map_source=queue_map_source,
        diff_error=diff_error,
        crc_fallback=crc_fallback,
    )


def _assert_query_queue_map(queue_map: dict, bundle) -> None:
    assert set(queue_map) == {bundle.expected_node_id}
    entry = queue_map[bundle.expected_node_id][0]
    primary_world = bundle.payload.world_ids[0]
    assert entry["queue"] == f"{primary_world}:alpha"


def _assert_diff_queue_map(queue_map: dict, bundle) -> None:
    assert queue_map == {"node123": [{"queue": "topic-A", "global": False}]}


def _assert_required_fields(result, expected_strategy_id: str, expected_sentinel: str) -> None:
    assert result.strategy_id == expected_strategy_id
    assert result.sentinel_id == expected_sentinel


def _assert_queue_map(
    result, expected_queue_map: dict | None, queue_map_assert: Callable[[dict], None] | None
) -> None:
    if expected_queue_map is not None:
        assert result.queue_map == expected_queue_map
    if queue_map_assert is not None:
        queue_map_assert(result.queue_map)


def _assert_flags(
    result,
    *,
    downgraded: bool,
    safe_mode: bool,
    downgrade_reason: Any,
    queue_map_source: str | None,
    diff_error: bool | None,
    crc_fallback: bool | None,
) -> None:
    assert result.downgraded is downgraded
    assert result.safe_mode is safe_mode
    assert result.downgrade_reason == downgrade_reason
    if queue_map_source is not None:
        assert result.queue_map_source == queue_map_source
    if diff_error is not None:
        assert result.diff_error is diff_error
    if crc_fallback is not None:
        assert result.crc_fallback is crc_fallback


@pytest.mark.parametrize(
    (
        "config",
        "bundle_mutation",
        "expected_sentinel",
        "queue_map_checker",
        "expected_tag_domain",
        "expected_bindings",
        "expected_world_calls",
        "expected_queue_source",
        "expected_diff_error",
        "expected_crc_fallback",
    ),
    [
        pytest.param(
            StrategySubmissionConfig(submit=True, diff_timeout=0.1),
                lambda bundle: setattr(bundle.payload, "world_ids", ["world-2"]),
                "diff-sentinel",
                _assert_query_queue_map,
                "dryrun",
                [
                    ("world-2", "strategy-abc"),
                ],
                [
                    ("world-2", {"strategies": ["strategy-abc"]}),
                ],
            "tag_query",
            False,
            False,
            id="submit-queries",
        ),
        pytest.param(
            StrategySubmissionConfig(
                submit=False,
                strategy_id="dryrun",
                diff_timeout=0.5,
                prefer_diff_queue_map=True,
                sentinel_default="",
                diff_strategy_id="dryrun",
                use_crc_sentinel_fallback=True,
            ),
            None,
            "diff-sentinel",
            _assert_diff_queue_map,
            None,
            [],
            [],
            "diff",
            False,
            False,
            id="dryrun-prefer-diff",
        ),
    ],
)
async def test_process_generates_queue_outputs(
    config: StrategySubmissionConfig,
    bundle_mutation,
    expected_sentinel: str,
    queue_map_checker,
    expected_tag_domain,
    expected_bindings,
    expected_world_calls,
    expected_queue_source,
    expected_diff_error,
    expected_crc_fallback,
    dummy_manager: DummyManager,
    dummy_dag_manager: DummyDagManager,
    dummy_database: DummyDatabase,
    stub_world_client_factory,
):
    world_client = stub_world_client_factory()
    helper = StrategySubmissionHelper(
        dummy_manager, dummy_dag_manager, dummy_database, world_client=world_client
    )
    bundle = build_strategy_payload()
    if bundle_mutation is not None:
        bundle_mutation(bundle)

    result = await helper.process(bundle.payload, config)

    _assert_process_outcome(
        result=result,
        config=config,
        bundle=bundle,
        queue_map_checker=queue_map_checker,
        expected_sentinel=expected_sentinel,
        expected_tag_domain=expected_tag_domain,
        expected_bindings=expected_bindings,
        expected_world_calls=expected_world_calls,
        expected_queue_source=expected_queue_source,
        expected_diff_error=expected_diff_error,
        expected_crc_fallback=expected_crc_fallback,
        dummy_manager=dummy_manager,
        dummy_dag_manager=dummy_dag_manager,
        dummy_database=dummy_database,
        world_client=world_client,
    )


def _assert_process_outcome(
    *,
    result,
    config: StrategySubmissionConfig,
    bundle,
    queue_map_checker,
    expected_sentinel: str,
    expected_tag_domain,
    expected_bindings,
    expected_world_calls,
    expected_queue_source,
    expected_diff_error,
    expected_crc_fallback,
    dummy_manager: DummyManager,
    dummy_dag_manager: DummyDagManager,
    dummy_database: DummyDatabase,
    world_client,
) -> None:
    expected_strategy_id = (
        "strategy-abc" if config.submit else (config.strategy_id or "dryrun")
    )
    assert_submission_result(
        result,
        expected_strategy_id=expected_strategy_id,
        expected_sentinel=expected_sentinel,
        queue_map_assert=lambda qm: queue_map_checker(qm, bundle),
        queue_map_source=expected_queue_source,
        diff_error=expected_diff_error,
        crc_fallback=expected_crc_fallback,
    )

    assert dummy_dag_manager.diff_calls
    _assert_tag_query(dummy_dag_manager, expected_tag_domain)
    _assert_submission_context(config, dummy_manager)
    _assert_bindings(dummy_database, expected_bindings)
    _assert_world_calls(world_client, expected_world_calls)


def _assert_tag_query(dummy_dag_manager: DummyDagManager, expected_tag_domain) -> None:
    if expected_tag_domain is None:
        assert not dummy_dag_manager.tag_queries
        return
    assert dummy_dag_manager.diff_calls[0][2] == expected_tag_domain
    assert dummy_dag_manager.tag_queries
    assert dummy_dag_manager.tag_queries[0][-1] == expected_tag_domain


def _assert_submission_context(
    config: StrategySubmissionConfig, dummy_manager: DummyManager
) -> None:
    if not config.submit:
        return
    assert dummy_manager.contexts
    assert isinstance(dummy_manager.contexts[0], StrategyComputeContext)


def _assert_bindings(dummy_database: DummyDatabase, expected_bindings) -> None:
    if expected_bindings is None:
        return
    assert dummy_database.bindings == expected_bindings


def _assert_world_calls(world_client, expected_world_calls) -> None:
    if expected_world_calls is None:
        return
    assert world_client.calls == expected_world_calls


async def test_process_dryrun_missing_as_of_downgrades_to_backtest(
    reset_gateway_metrics,
    dummy_manager: DummyManager,
    dummy_dag_manager: DummyDagManager,
    dummy_database: DummyDatabase,
):
    helper = StrategySubmissionHelper(dummy_manager, dummy_dag_manager, dummy_database)
    bundle = build_strategy_payload(
        execution_domain="dryrun",
        include_as_of=False,
    )

    result = await helper.process(
        bundle.payload,
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.3,
        ),
    )

    assert_submission_result(
        result,
        expected_strategy_id="dryrun",
        expected_sentinel="diff-sentinel",
        queue_map_assert=lambda qm: _assert_query_queue_map(qm, bundle),
        downgraded=True,
        downgrade_reason=DowngradeReason.MISSING_AS_OF,
        safe_mode=True,
    )
    _, _, domain, as_of, _, _ = dummy_dag_manager.diff_calls[0]
    assert domain == "backtest"
    assert as_of is None
    assert dummy_dag_manager.tag_queries[0][-1] == "backtest"
    metric_value = (
        metrics.strategy_compute_context_downgrade_total.labels(
            reason=DowngradeReason.MISSING_AS_OF.value
        )._value.get()
    )
    assert metric_value == 1


async def test_process_backtest_missing_as_of_enters_safe_mode(
    reset_gateway_metrics,
    dummy_manager: DummyManager,
    dummy_dag_manager: DummyDagManager,
    dummy_database: DummyDatabase,
):
    helper = StrategySubmissionHelper(dummy_manager, dummy_dag_manager, dummy_database)
    bundle = build_strategy_payload(
        execution_domain="backtest",
        include_as_of=False,
    )

    result = await helper.process(
        bundle.payload,
        StrategySubmissionConfig(
            submit=True,
            diff_timeout=0.2,
        ),
    )

    assert_submission_result(
        result,
        expected_strategy_id="strategy-abc",
        expected_sentinel="diff-sentinel",
        queue_map_assert=lambda qm: _assert_query_queue_map(qm, bundle),
        downgraded=True,
        downgrade_reason=DowngradeReason.MISSING_AS_OF,
        safe_mode=True,
    )
    _, _, domain, as_of, _, _ = dummy_dag_manager.diff_calls[0]
    assert domain == "backtest"
    assert as_of is None
    assert dummy_manager.skip_flags == [True]
    metric_value = (
        metrics.strategy_compute_context_downgrade_total.labels(
            reason=DowngradeReason.MISSING_AS_OF.value
        )._value.get()
    )
    assert metric_value == 1


async def test_process_dryrun_synonym_with_as_of_keeps_domain(
    reset_gateway_metrics,
    dummy_manager: DummyManager,
    dummy_dag_manager: DummyDagManager,
    dummy_database: DummyDatabase,
):
    helper = StrategySubmissionHelper(dummy_manager, dummy_dag_manager, dummy_database)
    bundle = build_strategy_payload(execution_domain="paper")

    await helper.process(
        bundle.payload,
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.3,
        ),
    )

    _, _, domain, as_of, _, _ = dummy_dag_manager.diff_calls[0]
    assert domain == "dryrun"
    assert as_of == "2025-01-01T00:00:00Z"
    assert dummy_dag_manager.tag_queries[0][-1] == "dryrun"
    metric_value = (
        metrics.strategy_compute_context_downgrade_total.labels(
            reason=DowngradeReason.MISSING_AS_OF.value
        )._value.get()
    )
    assert metric_value == 0


@pytest.mark.parametrize(
    "config",
    [
        StrategySubmissionConfig(submit=True, diff_timeout=0.1),
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.5,
            prefer_diff_queue_map=True,
            sentinel_default="",
            diff_strategy_id="dryrun",
            use_crc_sentinel_fallback=True,
        ),
    ],
    ids=["submit", "dry-run"],
)
async def test_shared_validation_path(
    config: StrategySubmissionConfig,
    dummy_manager: DummyManager,
    dummy_dag_manager: DummyDagManager,
    dummy_database: DummyDatabase,
):
    helper = StrategySubmissionHelper(dummy_manager, dummy_dag_manager, dummy_database)
    bundle = build_strategy_payload(mismatch=True)

    with pytest.raises(HTTPException) as exc:
        await helper.process(bundle.payload, config)

    detail = cast(dict[str, Any], exc.value.detail)
    assert detail["code"] == "E_NODE_ID_MISMATCH"


async def test_dry_run_diff_failure_falls_back_to_queries_and_crc(
    dummy_manager: DummyManager,
    dummy_dag_manager: DummyDagManager,
    dummy_database: DummyDatabase,
):
    dummy_dag_manager.raise_diff = True
    helper = StrategySubmissionHelper(dummy_manager, dummy_dag_manager, dummy_database)
    bundle = build_strategy_payload()

    result = await helper.process(
        bundle.payload,
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.5,
            prefer_diff_queue_map=True,
            sentinel_default="",
            diff_strategy_id="dryrun",
            use_crc_sentinel_fallback=True,
        ),
    )

    expected_crc = crc32_of_list(
        n.get("node_id", "") for n in bundle.dag.get("nodes", [])
    )
    assert_submission_result(
        result,
        expected_strategy_id="dryrun",
        expected_sentinel=f"dryrun:{expected_crc:08x}",
        queue_map_assert=lambda qm: _assert_query_queue_map(qm, bundle),
        queue_map_source="tag_query",
        diff_error=True,
        crc_fallback=True,
    )


async def test_world_bindings_world_service_failure_logged(
    caplog, dummy_manager: DummyManager, dummy_dag_manager: DummyDagManager, dummy_database: DummyDatabase, stub_world_client_factory
) -> None:
    world_client = stub_world_client_factory(fail_with=RuntimeError("ws down"))
    helper = StrategySubmissionHelper(
        dummy_manager, dummy_dag_manager, dummy_database, world_client=world_client
    )
    bundle = build_strategy_payload()

    with caplog.at_level("WARNING"):
        await helper.process(
            bundle.payload,
            StrategySubmissionConfig(
                submit=True,
                diff_timeout=0.1,
            ),
        )

    assert "WorldService binding sync failed" in caplog.text


async def test_world_bindings_persist_for_all_databases(
    world_binding_db_builder,
    monkeypatch,
    dummy_manager: DummyManager,
    dummy_dag_manager: DummyDagManager,
    stub_world_client_factory,
):
    db, fetch_bindings, cleanup = await world_binding_db_builder(monkeypatch)
    world_client = stub_world_client_factory(conflict_after={2})
    helper = StrategySubmissionHelper(
        dummy_manager, dummy_dag_manager, db, world_client=world_client
    )
    bundle = build_strategy_payload()
    config = StrategySubmissionConfig(submit=True, diff_timeout=0.1)

    try:
        await helper.process(bundle.payload, config)
        await helper.process(bundle.payload, config)
        bindings = await fetch_bindings()
        assert bindings == {("world-1", "strategy-abc")}
        assert [call[0] for call in world_client.calls] == ["world-1", "world-1"]
        assert all(
            call[1] == {"strategies": ["strategy-abc"]}
            for call in world_client.calls
        )
    finally:
        await cleanup()
