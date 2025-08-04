from qmtl.indicators import sma
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


def test_sma_compute():
    src = SourceNode(interval="1s", period=3)
    node = sma(src, window=2)
    data = {src.node_id: {1: [(0, 1), (1, 3)]}}
    view = CacheView(data)
    assert node.compute_fn(view) == 2

from qmtl.indicators import (
    ema,
    rsi,
    bollinger_bands,
    atr,
    chandelier_exit,
    vwap,
    anchored_vwap,
    keltner_channel,
    obv,
    supertrend,
    ichimoku_cloud,
    kalman_trend,
    rough_bergomi,
    stoch_rsi,
    kdj,
)


def test_ema_compute():
    src = SourceNode(interval="1s", period=3)
    node = ema(src, window=3)
    data = {src.node_id: {1: [(0, 1), (1, 2), (2, 3)]}}
    view = CacheView(data)
    assert node.compute_fn(view) == 2.25


def test_rsi_compute():
    src = SourceNode(interval="1s", period=15)
    node = rsi(src, window=14)
    data = {src.node_id: {1: [(i, float(i)) for i in range(15)]}}
    view = CacheView(data)
    assert node.compute_fn(view) == 100.0


def test_bollinger_bands_compute():
    src = SourceNode(interval="1s", period=3)
    node = bollinger_bands(src, window=3)
    data = {src.node_id: {1: [(0, 1), (1, 2), (2, 3)]}}
    view = CacheView(data)
    result = node.compute_fn(view)
    assert round(result["mid"], 2) == 2.0
    assert round(result["upper"], 3) == 3.633
    assert round(result["lower"], 3) == 0.367


def test_atr_compute():
    h = SourceNode(interval="1s", period=3, config={"id": "h"})
    l = SourceNode(interval="1s", period=3, config={"id": "l"})
    c = SourceNode(interval="1s", period=4, config={"id": "c"})
    node = atr(h, l, c, window=3)
    data = {
        h.node_id: {1: [(0, 2), (1, 3), (2, 4)]},
        l.node_id: {1: [(0, 0), (1, 1), (2, 2)]},
        c.node_id: {1: [(0, 1), (1, 2), (2, 3), (3, 4)]},
    }
    view = CacheView(data)
    assert node.compute_fn(view) == 2


def test_chandelier_exit_compute():
    h = SourceNode(interval="1s", period=3, config={"id": "h"})
    l = SourceNode(interval="1s", period=3, config={"id": "l"})
    c = SourceNode(interval="1s", period=4, config={"id": "c"})
    node = chandelier_exit(h, l, c, window=3, multiplier=3)
    data = {
        h.node_id: {1: [(0, 2), (1, 3), (2, 4)]},
        l.node_id: {1: [(0, 0), (1, 1), (2, 2)]},
        c.node_id: {1: [(0, 1), (1, 2), (2, 3), (3, 4)]},
    }
    view = CacheView(data)
    result = node.compute_fn(view)
    assert result["long"] == -2
    assert result["short"] == 6


def test_vwap_compute():
    p = SourceNode(interval="1s", period=3, config={"id": "p"})
    v = SourceNode(interval="1s", period=3, config={"id": "v"})
    node = vwap(p, v, window=3)
    data = {
        p.node_id: {1: [(0, 1), (1, 2), (2, 3)]},
        v.node_id: {1: [(0, 1), (1, 1), (2, 2)]},
    }
    view = CacheView(data)
    assert node.compute_fn(view) == 2.25


def test_anchored_vwap_compute():
    p = SourceNode(interval="1s", period=3, config={"id": "p"})
    v = SourceNode(interval="1s", period=3, config={"id": "v"})
    node = anchored_vwap(p, v, anchor_ts=1)
    data = {
        p.node_id: {1: [(0, 1), (1, 2), (2, 3)]},
        v.node_id: {1: [(0, 1), (1, 1), (2, 1)]},
    }
    view = CacheView(data)
    assert node.compute_fn(view) == 2.5


def test_keltner_channel_compute():
    h = SourceNode(interval="1s", period=3, config={"id": "h"})
    l = SourceNode(interval="1s", period=3, config={"id": "l"})
    c = SourceNode(interval="1s", period=4, config={"id": "c"})
    node = keltner_channel(h, l, c, ema_window=3, atr_window=3, multiplier=2)
    data = {
        h.node_id: {1: [(0, 2), (1, 3), (2, 4)]},
        l.node_id: {1: [(0, 0), (1, 1), (2, 2)]},
        c.node_id: {1: [(0, 1), (1, 2), (2, 3), (3, 4)]},
    }
    view = CacheView(data)
    result = node.compute_fn(view)
    assert round(result["mid"], 2) == 3.25
    assert round(result["upper"], 2) == 7.25
    assert round(result["lower"], 2) == -0.75


def test_obv_compute():
    c = SourceNode(interval="1s", period=3, config={"id": "c"})
    v = SourceNode(interval="1s", period=3, config={"id": "v"})
    node = obv(c, v)
    data = {
        c.node_id: {1: [(0, 1), (1, 2), (2, 1)]},
        v.node_id: {1: [(0, 10), (1, 5), (2, 3)]},
    }
    view = CacheView(data)
    assert node.compute_fn(view) == 2


def test_supertrend_compute():
    h = SourceNode(interval="1s", period=3, config={"id": "h"})
    l = SourceNode(interval="1s", period=3, config={"id": "l"})
    c = SourceNode(interval="1s", period=4, config={"id": "c"})
    node = supertrend(h, l, c, window=3, multiplier=2)
    data = {
        h.node_id: {1: [(0, 2), (1, 3), (2, 4)]},
        l.node_id: {1: [(0, 0), (1, 1), (2, 2)]},
        c.node_id: {1: [(0, 1), (1, 2), (2, 3), (3, 4)]},
    }
    view = CacheView(data)
    assert node.compute_fn(view) == -1


def test_ichimoku_cloud_compute():
    h = SourceNode(interval="1s", period=52, config={"id": "h"})
    l = SourceNode(interval="1s", period=52, config={"id": "l"})
    c = SourceNode(interval="1s", period=52, config={"id": "c"})
    node = ichimoku_cloud(h, l, c)
    highs = [(i, i + 1) for i in range(52)]
    lows = [(i, i) for i in range(52)]
    closes = [(i, i + 0.5) for i in range(52)]
    data = {h.node_id: {1: highs}, l.node_id: {1: lows}, c.node_id: {1: closes}}
    view = CacheView(data)
    result = node.compute_fn(view)
    assert result["tenkan"] == 47.5
    assert result["kijun"] == 39
    assert result["senkou_b"] == 26


def test_kalman_trend_compute():
    src = SourceNode(interval="1s", period=5, config={"id": "src"})
    node = kalman_trend(src)
    data = {src.node_id: {1: [(i, float(i)) for i in range(5)]}}
    view = CacheView(data)
    result = node.compute_fn(view)
    assert isinstance(result, float)


def test_rough_bergomi_compute():
    src = SourceNode(interval="1s", period=4, config={"id": "src"})
    node = rough_bergomi(src, window=3)
    data = {src.node_id: {1: [(0, 1), (1, 2), (2, 1), (3, 2)]}}
    view = CacheView(data)
    assert round(node.compute_fn(view), 4) > 0


def test_stoch_rsi_compute():
    src = SourceNode(interval="1s", period=30, config={"id": "src"})
    node = stoch_rsi(src, window=14)
    values = [(i, float(i % 5)) for i in range(30)]
    data = {src.node_id: {1: values}}
    view = CacheView(data)
    result = node.compute_fn(view)
    assert 0 <= result <= 100


def test_kdj_compute():
    h = SourceNode(interval="1s", period=3, config={"id": "h"})
    l = SourceNode(interval="1s", period=3, config={"id": "l"})
    c = SourceNode(interval="1s", period=3, config={"id": "c"})
    node = kdj(h, l, c, window=3)
    data = {
        h.node_id: {1: [(0, 3), (1, 4), (2, 5)]},
        l.node_id: {1: [(0, 1), (1, 1), (2, 2)]},
        c.node_id: {1: [(0, 2), (1, 3), (2, 4)]},
    }
    view = CacheView(data)
    result = node.compute_fn(view)
    assert result["K"] == result["D"] == result["J"]
