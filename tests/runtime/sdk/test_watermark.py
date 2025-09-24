import pytest

from qmtl.runtime.sdk.node import Node, ProcessingNode
from qmtl.runtime.sdk.watermark import (
    WatermarkGate,
    clear_watermarks,
    get_watermark,
    set_watermark,
)


def _mk_node(on_late: str = "recompute", allowed_lateness: int = 0) -> ProcessingNode:
    def compute(view):
        # Return latest of upstream for assertion purposes
        items = view["N1"][60].latest()
        return items

    # Single upstream processing node; cache period=2 for quick warmup
    n = ProcessingNode(
        input=Node(input=None, compute_fn=None, name="src", interval=60, period=2, tags=[]),
        compute_fn=compute,
        name="proc",
        interval=60,
        period=2,
        tags=[],
        allowed_lateness=allowed_lateness,
        on_late=on_late,
    )
    return n


def test_watermark_and_gating_recompute():
    n = _mk_node(on_late="recompute", allowed_lateness=0)
    # warmup fill
    assert n.feed("N1", 60, 60, {"a": 1}) is False
    assert n.feed("N1", 60, 120, {"a": 2}) is True
    assert n.watermark() == 120  # min(last_ts) - 0
    # late event arrives
    assert n.feed("N1", 60, 60, {"a": 3}) is True  # recompute on late


def test_watermark_late_ignore_and_side_output():
    n_ignore = _mk_node(on_late="ignore", allowed_lateness=0)
    n_ignore.feed("N1", 60, 60, 1)
    n_ignore.feed("N1", 60, 120, 2)
    assert n_ignore.watermark() == 120
    assert n_ignore.feed("N1", 60, 60, 3) is False

    n_side = _mk_node(on_late="side_output", allowed_lateness=0)
    n_side.feed("N1", 60, 60, 1)
    n_side.feed("N1", 60, 120, 2)
    assert n_side.feed("N1", 60, 60, 3) is False
    assert getattr(n_side, "_late_events", None) and n_side._late_events[-1][1] == 60


def test_watermark_gate_helpers():
    gate = WatermarkGate(enabled=True, lag=2)
    assert gate.required_timestamp(180, 60) == 60
    assert gate.required_timestamp(120, None) == 118

    simulate_gate = WatermarkGate.for_mode("simulate")
    assert simulate_gate.enabled is False
    live_gate = WatermarkGate.for_mode("live")
    assert live_gate.enabled is True
    override_gate = WatermarkGate.for_mode("simulate", enabled=True, lag=3)
    assert override_gate.enabled is True and override_gate.lag == 3


def test_clear_watermarks_resets_state():
    clear_watermarks()
    set_watermark("topic", "world", 100)
    assert get_watermark("topic", "world") == 100
    clear_watermarks()
    assert get_watermark("topic", "world") is None

