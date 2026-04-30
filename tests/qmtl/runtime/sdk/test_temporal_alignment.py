from __future__ import annotations

import pytest

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import ProcessingNode, StreamInput
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.sdk.temporal import (
    AlignmentInputSpec,
    JoinSpec,
    TemporalAlignedOutputSpec,
    TemporalSpec,
    WatermarkPolicy,
    infer_join_specs,
)


def _kr_equity_view() -> CacheView:
    return CacheView(
        {
            "daily": {
                86400: [
                    (1_000, {"symbol": "005930", "close": 70_000, "is_final": True}),
                    (2_000, {"symbol": "005930", "close": 71_000, "is_final": False}),
                    (1_000, {"symbol": "000660", "close": 120_000, "is_final": True}),
                ]
            },
            "hourly": {
                3600: [
                    (1_900, {"symbol": "005930", "close": 70_500, "is_final": True}),
                    (2_080, {"symbol": "005930", "close": 70_700, "is_final": False}),
                ]
            },
            "book": {
                1: [
                    (
                        2_100,
                        {
                            "symbol": "005930",
                            "bid": 70_450,
                            "ask": 70_500,
                            "quality": "ok",
                        },
                    )
                ]
            },
        }
    )


def test_daily_hourly_closed_bars_align_to_orderbook_trigger():
    aligned = _kr_equity_view().align_temporal(
        {
            "daily": JoinSpec(
                "daily",
                86400,
                mode="asof",
                temporal=TemporalSpec(kind="bar"),
                partition_key="symbol",
            ),
            "hourly": JoinSpec(
                "hourly",
                3600,
                mode="asof",
                temporal=TemporalSpec(kind="bar"),
                partition_key="symbol",
            ),
            "book": JoinSpec(
                "book",
                1,
                mode="exact",
                closed_only=False,
                temporal=TemporalSpec(kind="event"),
                partition_key="symbol",
            ),
        },
        trigger_ts=2_100,
        partition={"symbol": "005930"},
    )

    assert aligned.ready is True
    assert aligned["daily"]["close"] == 70_000
    assert aligned["hourly"]["close"] == 70_500
    assert aligned["book"]["ask"] == 70_500
    assert aligned.status.selected_ts == {
        "daily": 1_000,
        "hourly": 1_900,
        "book": 2_100,
    }


def test_bounded_asof_marks_stale_orderbook_snapshot():
    view = CacheView(
        {
            "hourly": {3600: [(3_600, {"symbol": "005930", "is_final": True})]},
            "book": {1: [(3_590, {"symbol": "005930", "bid": 1, "ask": 2})]},
        }
    )

    aligned = view.align_temporal(
        {
            "hourly": JoinSpec("hourly", 3600, mode="exact"),
            "book": JoinSpec(
                "book",
                1,
                mode="asof",
                tolerance="5s",
                closed_only=False,
            ),
        },
        trigger_ts=3_600,
    )

    assert aligned.ready is False
    assert aligned.status.reason == "stale_inputs"
    assert aligned.status.stale_inputs == ("book",)
    assert aligned.status.age_ms["book"] == 10_000


def test_missing_optional_hourly_input_does_not_block_session_open():
    view = CacheView(
        {
            "daily": {86400: [(1_000, {"symbol": "005930", "is_final": True})]},
            "book": {1: [(1_100, {"symbol": "005930", "bid": 1, "ask": 2})]},
        }
    )

    aligned = view.align_temporal(
        {
            "daily": JoinSpec("daily", 86400, mode="temporal"),
            "hourly": JoinSpec("hourly", 3600, mode="asof", required=False),
            "book": JoinSpec("book", 1, mode="exact", closed_only=False),
        },
        trigger_ts=1_100,
    )

    assert aligned.ready is True
    assert aligned["hourly"] is None
    assert aligned.status.missing_inputs == ("hourly",)
    assert aligned.status.inputs["hourly"].required is False


def test_partitioned_alignment_selects_symbol_specific_rows():
    aligned = _kr_equity_view().align_temporal(
        {
            "daily": JoinSpec(
                "daily",
                86400,
                mode="asof",
                partition_key="symbol",
            )
        },
        trigger_ts=2_100,
        partition={"symbol": "000660"},
    )

    assert aligned.ready is True
    assert aligned["daily"]["symbol"] == "000660"
    assert aligned["daily"]["close"] == 120_000


def test_orderbook_sequence_gap_blocks_required_input():
    view = CacheView(
        {
            "book": {
                1: [
                    (
                        2_100,
                        {
                            "symbol": "005930",
                            "bid": 1,
                            "ask": 2,
                            "sequence_gap": True,
                        },
                    )
                ]
            }
        }
    )

    aligned = view.align_temporal(
        {
            "book": JoinSpec(
                "book",
                1,
                mode="exact",
                closed_only=False,
                temporal=TemporalSpec(kind="event", sequence="seq"),
            )
        },
        trigger_ts=2_100,
    )

    assert aligned.ready is False
    assert aligned.status.reason == "quality"
    assert aligned.status.quality_inputs == {"book": "sequence_gap"}


def test_watermark_policy_defaults_late_behavior_by_execution_domain():
    assert WatermarkPolicy.for_execution_domain("live").late == "side_output"
    assert WatermarkPolicy.for_execution_domain("paper").late == "side_output"
    assert WatermarkPolicy.for_execution_domain("backtest").late == "recompute"
    assert WatermarkPolicy.for_execution_domain("simulate").late == "recompute"


def test_streaminput_accepts_temporal_spec_and_daily_interval_alias():
    stream = StreamInput(
        tags=["krx", "book"],
        interval="1d",
        period=1,
        temporal=TemporalSpec(kind="event", idle_after="2s", sequence="seq"),
        alignment=AlignmentInputSpec(alias="book", partition_key="symbol"),
    )

    assert stream.interval == 86400
    assert stream.temporal is not None
    assert stream.temporal.kind == "event"
    assert stream.alignment is not None
    assert stream.alignment.alias == "book"
    assert stream.config["temporal"]["kind"] == "event"
    assert stream.config["temporal"]["sequence"] == "seq"
    assert stream.config["alignment"]["alias"] == "book"


def test_infer_join_specs_from_temporal_stream_metadata():
    daily = StreamInput(interval="1d", period=1, temporal=TemporalSpec(kind="bar"))
    book = StreamInput(
        interval="1s",
        period=1,
        temporal=TemporalSpec(kind="event", idle_after="2s", sequence="seq"),
    )

    specs = infer_join_specs(
        {"daily": daily, "book": book},
        trigger=book,
        partition_key="symbol",
    )

    assert specs["daily"].node is daily
    assert specs["daily"].interval_value == 86400
    assert specs["daily"].mode == "asof"
    assert specs["daily"].closed_only is True
    assert specs["daily"].partition_key == "symbol"
    assert specs["book"].mode == "exact"
    assert specs["book"].closed_only is False
    assert specs["book"].max_age is None


def test_align_temporal_infers_context_event_freshness_from_idle_after():
    hourly = StreamInput(interval="1h", period=1, temporal=TemporalSpec(kind="bar"))
    book = StreamInput(
        interval="1s",
        period=1,
        temporal=TemporalSpec(kind="event", idle_after="5s"),
    )
    view = CacheView(
        {
            hourly.node_id: {hourly.interval: [(3_600, {"is_final": True})]},
            book.node_id: {book.interval: [(3_590, {"bid": 1, "ask": 2})]},
        }
    )

    aligned = view.align_temporal(
        {"hourly": hourly, "book": book},
        trigger=hourly,
        trigger_ts=3_600,
    )

    assert aligned.ready is False
    assert aligned.status.reason == "stale_inputs"
    assert aligned.status.stale_inputs == ("book",)
    assert aligned.status.age_ms["book"] == 10_000


def test_join_inference_requires_temporal_metadata():
    book = StreamInput(interval="1s", period=1)

    with pytest.raises(ValueError, match="no temporal metadata"):
        infer_join_specs({"book": book}, trigger=book)


def test_join_inference_rejects_unbounded_event_context_without_override():
    hourly = StreamInput(interval="1h", period=1, temporal=TemporalSpec(kind="bar"))
    book = StreamInput(interval="1s", period=1, temporal=TemporalSpec(kind="event"))

    with pytest.raises(ValueError, match="event/state context inputs require"):
        infer_join_specs({"hourly": hourly, "book": book}, trigger=hourly)

    specs = infer_join_specs(
        {"hourly": hourly, "book": book},
        trigger=hourly,
        overrides={"book": {"max_age": "1s"}},
    )
    assert specs["book"].mode == "asof"
    assert specs["book"].closed_only is False
    assert specs["book"].max_age == "1s"


def test_temporal_aligned_output_node_materializes_aligned_payload():
    daily = StreamInput(
        interval="1d",
        period=1,
        temporal=TemporalSpec(kind="bar"),
        alignment=AlignmentInputSpec(alias="daily", partition_key="symbol"),
    )
    book = StreamInput(
        interval="1s",
        period=1,
        temporal=TemporalSpec(kind="event", idle_after="2s", sequence="seq"),
        alignment=AlignmentInputSpec(alias="book", partition_key="symbol"),
    )
    node = ProcessingNode(
        input=[daily, book],
        output=TemporalAlignedOutputSpec(trigger=book, partition_key="symbol"),
        interval="1s",
        period=1,
    )

    assert Runner.feed_queue_data(
        node,
        daily.node_id,
        daily.interval,
        1_000,
        {"symbol": "005930", "close": 70_000, "is_final": True},
    ) is None
    aligned = Runner.feed_queue_data(
        node,
        book.node_id,
        book.interval,
        1_100,
        {"symbol": "005930", "bid": 69_950, "ask": 70_000},
    )

    assert node.compute_fn is None
    assert node.config["output"]["kind"] == "temporal_aligned"
    assert aligned is not None
    assert aligned.ready is True
    assert aligned.partition == {"symbol": "005930"}
    assert aligned["daily"]["close"] == 70_000
    assert aligned["book"]["ask"] == 70_000


def test_temporal_aligned_output_only_executes_on_trigger_feed():
    daily = StreamInput(
        interval="1d",
        period=1,
        temporal=TemporalSpec(kind="bar"),
        alignment=AlignmentInputSpec(alias="daily"),
    )
    book = StreamInput(
        interval="1s",
        period=1,
        temporal=TemporalSpec(kind="event", idle_after="2s"),
        alignment=AlignmentInputSpec(alias="book"),
    )
    node = ProcessingNode(
        input=[daily, book],
        output=TemporalAlignedOutputSpec(trigger=book),
        interval="1s",
        period=1,
    )

    assert Runner.feed_queue_data(node, daily.node_id, daily.interval, 1_000, {"close": 70_000}) is None
    result = Runner.feed_queue_data(
        node,
        book.node_id,
        book.interval,
        1_100,
        {"bid": 69_950, "ask": 70_000},
    )

    assert result is not None
    assert result.ready is True
    assert result["daily"]["close"] == 70_000


def test_temporal_aligned_output_rejects_missing_alias():
    book = StreamInput(
        interval="1s",
        period=1,
        temporal=TemporalSpec(kind="event", idle_after="2s"),
    )

    with pytest.raises(ValueError, match="requires alignment alias"):
        ProcessingNode(
            input=[book],
            output=TemporalAlignedOutputSpec(trigger=book),
            interval="1s",
            period=1,
        )


def test_temporal_aligned_output_rejects_unbounded_context_event():
    hourly = StreamInput(
        interval="1h",
        period=1,
        temporal=TemporalSpec(kind="bar"),
        alignment=AlignmentInputSpec(alias="hourly"),
    )
    book = StreamInput(
        interval="1s",
        period=1,
        temporal=TemporalSpec(kind="event"),
        alignment=AlignmentInputSpec(alias="book"),
    )

    with pytest.raises(ValueError, match="event/state context inputs require"):
        ProcessingNode(
            input=[hourly, book],
            output=TemporalAlignedOutputSpec(trigger=hourly),
            interval="1h",
            period=1,
        )


def test_temporal_aligned_output_rejects_compute_fn():
    book = StreamInput(
        interval="1s",
        period=1,
        temporal=TemporalSpec(kind="event", idle_after="2s"),
        alignment=AlignmentInputSpec(alias="book"),
    )

    with pytest.raises(TypeError, match="must not define compute_fn"):
        ProcessingNode(
            input=[book],
            compute_fn=lambda view: view,
            output=TemporalAlignedOutputSpec(trigger=book),
            interval="1s",
            period=1,
        )


def test_temporal_aligned_output_ready_only_drops_not_ready_payload():
    hourly = StreamInput(
        interval="1h",
        period=1,
        temporal=TemporalSpec(kind="bar"),
        alignment=AlignmentInputSpec(alias="hourly"),
    )
    book = StreamInput(
        interval="1s",
        period=1,
        temporal=TemporalSpec(kind="event", idle_after="5s"),
        alignment=AlignmentInputSpec(alias="book"),
    )
    node = ProcessingNode(
        input=[hourly, book],
        output=TemporalAlignedOutputSpec(trigger=hourly),
        interval="1h",
        period=1,
    )

    assert Runner.feed_queue_data(
        node,
        book.node_id,
        book.interval,
        3_590,
        {"bid": 1, "ask": 2},
    ) is None
    assert Runner.feed_queue_data(
        node,
        hourly.node_id,
        hourly.interval,
        3_600,
        {"is_final": True},
    ) is None


def test_temporal_aligned_output_can_emit_not_ready_payload():
    hourly = StreamInput(
        interval="1h",
        period=1,
        temporal=TemporalSpec(kind="bar"),
        alignment=AlignmentInputSpec(alias="hourly"),
    )
    book = StreamInput(
        interval="1s",
        period=1,
        temporal=TemporalSpec(kind="event", idle_after="5s"),
        alignment=AlignmentInputSpec(alias="book"),
    )
    node = ProcessingNode(
        input=[hourly, book],
        output=TemporalAlignedOutputSpec(trigger=hourly, ready_only=False),
        interval="1h",
        period=1,
    )

    assert Runner.feed_queue_data(
        node,
        book.node_id,
        book.interval,
        3_590,
        {"bid": 1, "ask": 2},
    ) is None
    aligned = Runner.feed_queue_data(
        node,
        hourly.node_id,
        hourly.interval,
        3_600,
        {"is_final": True},
    )

    assert aligned is not None
    assert aligned.ready is False
    assert aligned.status.reason == "stale_inputs"
    assert aligned.status.stale_inputs == ("book",)


def test_late_policy_blocks_live_inputs_but_marks_backtest_recompute():
    view = CacheView(
        {
            "daily": {
                86400: [
                    (
                        1_000,
                        {
                            "close": 70_000,
                            "is_final": True,
                            "received_ts": 1_105,
                        },
                    )
                ]
            }
        }
    )
    inputs = {
        "daily": JoinSpec(
            "daily",
            86400,
            mode="asof",
            temporal=TemporalSpec(kind="bar", received_ts="received_ts"),
        )
    }

    live = view.align_temporal(
        inputs,
        trigger_ts=1_100,
        watermark_policy=WatermarkPolicy.for_execution_domain("live"),
    )
    backtest = view.align_temporal(
        inputs,
        trigger_ts=1_100,
        watermark_policy=WatermarkPolicy.for_execution_domain("backtest"),
    )

    assert live.ready is False
    assert live.status.reason == "late_inputs"
    assert live.status.late_inputs == ("daily",)
    assert live.status.inputs["daily"].late is True
    assert backtest.ready is True
    assert backtest.status.late_inputs == ("daily",)
    assert backtest.status.inputs["daily"].late is True
