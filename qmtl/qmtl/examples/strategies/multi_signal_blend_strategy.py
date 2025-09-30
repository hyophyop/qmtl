"""Example strategy blending multiple signals and attaching a Node Set.

This example shows a manual signal blender (no external combinators) and
attaches a Node Set built via the Steps DSL. Swap to the CCXT recipe for an
exchange-backed execution chain.
"""

from __future__ import annotations

from qmtl.runtime.sdk import Strategy, StreamInput, Node
from qmtl.runtime.nodesets.steps import pretrade, sizing, execution, fills, portfolio, risk, timing, compose


class MultiSignalBlendStrategy(Strategy):
    def setup(self) -> None:
        price = StreamInput(interval="60s", period=2)

        def alpha_a(view):
            data = view[price][price.interval]
            if len(data) < 2:
                return 0.0
            prev, last = data[-2][1]["close"], data[-1][1]["close"]
            return (last - prev) / prev

        def alpha_b(view):
            data = view[price][price.interval]
            return (sum(p[1]["close"] for p in data[-5:]) / 5.0) if len(data) >= 5 else 0.0

        a = Node(input=price, compute_fn=alpha_a, name="alpha_a", interval="60s", period=1)
        b = Node(input=price, compute_fn=alpha_b, name="alpha_b", interval="60s", period=1)

        def to_signal(threshold):
            def _fn(view):
                data = view[price][price.interval]
                if not data:
                    return {"action": "HOLD", "size": 0.0}
                alpha = data[-1][1]
                if alpha > threshold:
                    return {"action": "BUY", "size": 1.0, "symbol": "BTC/USDT"}
                if alpha < -threshold:
                    return {"action": "SELL", "size": 1.0, "symbol": "BTC/USDT"}
                return {"action": "HOLD", "size": 0.0}

            return _fn

        sig_a = Node(input=a, compute_fn=to_signal(0.0), name="sig_a", interval="60s", period=1)
        sig_b = Node(input=b, compute_fn=to_signal(0.0), name="sig_b", interval="60s", period=1)

        signals = [sig_a, sig_b]
        weights = [0.6, 0.4]

        def blend(view):
            score = 0.0
            for s, w in zip(signals, weights):
                data = view[s][s.interval]
                if not data:
                    return None
                v = data[-1][1]
                action = str(v.get("action", "HOLD")).upper()
                size = float(v.get("size", 0.0))
                signed = size if action == "BUY" else (-size if action == "SELL" else 0.0)
                score += w * signed
            if score > 0:
                return {"action": "BUY", "size": score, "symbol": "BTC/USDT"}
            if score < 0:
                return {"action": "SELL", "size": abs(score), "symbol": "BTC/USDT"}
            return {"action": "HOLD", "size": 0.0, "symbol": "BTC/USDT"}

        combined_signal = Node(input=signals, compute_fn=blend, name="signal_blend", interval="60s", period=1)

        # Attach a minimal Node Set (stubs) behind the blended signal
        nodeset = compose(combined_signal, steps=[pretrade(), sizing(), execution(), fills(), portfolio(), risk(), timing()])

        # Register nodes
        self.add_nodes([price, a, b, sig_a, sig_b, combined_signal, nodeset])

