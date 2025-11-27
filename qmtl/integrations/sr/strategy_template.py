"""Strategy template builder for expression-based SR outputs.

This keeps SR 통합을 코어와 느슨하게 결합시키면서,
Seamless Data Provider와 동일 데이터를 사용하도록 Strategy를 생성한다.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Mapping, Sequence, TYPE_CHECKING, cast

from .expression_key import compute_expression_key

try:
    from dataclasses import asdict as _dataclass_asdict
except Exception:  # pragma: no cover - fallback
    dataclass_asdict: Callable[[Any], dict[str, Any]] | None = None
else:
    dataclass_asdict = cast(Callable[[Any], dict[str, Any]], _dataclass_asdict)

_RUNTIME_AVAILABLE = False
if TYPE_CHECKING:
    from qmtl.runtime.sdk import Strategy
    from qmtl.runtime.sdk.node import ProcessingNode, StreamInput
else:
    try:  # pragma: no cover - optional at runtime
        from qmtl.runtime.sdk import Strategy
        from qmtl.runtime.sdk.node import StreamInput, ProcessingNode

        _RUNTIME_AVAILABLE = True
    except Exception:  # pragma: no cover - fallback for tests/docs
        class Strategy:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.nodes: list[Any] = []

            def add_nodes(self, nodes: Any) -> None:
                if not isinstance(nodes, Sequence):
                    nodes = [nodes]
                self.nodes.extend(list(nodes))

            def serialize(self) -> dict[str, Any]:
                return {"schema_version": "v1", "nodes": [], "meta": {}}

            def on_start(self) -> None: ...

            def on_finish(self) -> None: ...

            def setup(self) -> None: ...

        class StreamInput:
            def __init__(self, *, interval: Any = None, period: Any = None, history_provider: Any = None) -> None:
                self.interval = interval
                self.period = period
                self.history_provider = history_provider
                self.node_id = "stream_input"
                self.dataset_fingerprint = None

        class ProcessingNode:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.input = args[0] if args else None
                self.compute_fn = kwargs.get("compute_fn")
                self.interval = kwargs.get("interval")
                self.period = kwargs.get("period")
                self.tags = kwargs.get("tags", [])
                self.node_id = "processing_node"
                self.dataset_fingerprint = None


def _compile_expression(expression: str, modules: str | tuple[str, ...] = "numpy"):
    try:
        import sympy as sp

        parsed = sp.sympify(expression)
        symbols = sorted([str(s) for s in parsed.free_symbols])
        fn = sp.lambdify([sp.Symbol(s) for s in symbols], parsed, modules=modules)
        return parsed, symbols, fn
    except Exception:
        return None, [], None


def build_expression_strategy(
    expression: str,
    *,
    strategy_name: str | None = None,
    data_spec: Mapping[str, Any] | None = None,
    history_provider: Any | None = None,
    sr_engine: str | None = None,
    expression_key: str | None = None,
    expression_dag_spec: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> type[Strategy]:
    """Create a Strategy subclass that evaluates a given expression.

    Parameters
    ----------
    expression : str
        Expression string to evaluate.
    strategy_name : str, optional
        Explicit Strategy class name.
        data_spec : Mapping[str, Any], optional
            Snapshot handle (dataset_id, snapshot_version/as_of, partition, timeframe, etc.).
        history_provider : Any, optional
            Seamless Data Provider to feed StreamInput.
        sr_engine : str, optional
            SR engine identifier.
        expression_key : str, optional
            Precomputed expression key (if None, computed from expression).
        expression_dag_spec : Mapping, optional
            Canonical DAG spec (if available).
        metadata : Mapping, optional
            Additional SR metadata (candidate_id, fitness, complexity, generation, etc.).
    """
    parsed, symbols, fn = _compile_expression(expression)
    expr_key = expression_key or compute_expression_key(expression)
    interval = None
    period = None
    if isinstance(data_spec, Mapping):
        interval = data_spec.get("interval") or data_spec.get("timeframe")
        period = data_spec.get("period") or data_spec.get("min_history")

    class ExpressionStrategy(Strategy):
        _expression = expression
        _data_spec = dict(data_spec) if isinstance(data_spec, Mapping) else None
        _sr_engine = sr_engine
        _compiled = (parsed, symbols, fn)
        _expression_key = expr_key
        _expression_dag_spec = (
            dict(expression_dag_spec) if isinstance(expression_dag_spec, Mapping) else None
        )
        _sr_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}

        def setup(self) -> None:  # pragma: no cover - simple wiring
            if not _RUNTIME_AVAILABLE:
                return

            stream = StreamInput(
                interval=interval or "60s",
                period=period or 200,
                history_provider=history_provider,
            )

            def _compute(view: Any) -> Any:
                try:
                    window = view[stream.node_id][stream.interval]
                    latest = window.latest()
                    rows = getattr(window, "_data", None)
                except Exception:
                    return None
                ts = None
                payload = latest
                try:
                    from collections.abc import Sequence as _Seq

                    if isinstance(rows, _Seq) and rows:
                        ts, payload = rows[-1]
                except Exception:
                    pass
                value = self._evaluate_payload(payload)
                if value is None:
                    return None
                return {"ts": ts, "value": value, "signal": value}

            signal_node = ProcessingNode(
                stream,
                compute_fn=_compute,
                name="sr_signal",
                interval=stream.interval,
                period=stream.period,
                tags=["sr"],
            )

            # dataset_fingerprint propagate if present
            fingerprint = None
            if self._data_spec:
                ds = self._data_spec.get("dataset_id")
                snap = self._data_spec.get("snapshot_version") or self._data_spec.get("as_of")
                if ds and snap:
                    fingerprint = f"{ds}:{snap}"
            if fingerprint:
                for node_obj in (stream, signal_node):
                    try:
                        node_obj.dataset_fingerprint = fingerprint
                    except Exception:
                        continue

            self.add_nodes([stream, signal_node])

        def _evaluate_payload(self, payload: Any) -> float | None:
            parsed_local, sym_local, fn_local = self._compiled
            if fn_local is None:
                return None
            if not sym_local:
                try:
                    return float(fn_local())
                except Exception:
                    return None
            vals: list[Any] = []
            for name in sym_local:
                if isinstance(payload, Mapping):
                    vals.append(payload.get(name))
                else:
                    vals.append(payload)
            if any(v is None for v in vals):
                return None
            try:
                return float(fn_local(*vals))
            except Exception:
                return None

        def evaluate(self, payload: Any) -> float | None:
            """Evaluate expression on a mapping payload (for tests/docs)."""
            return self._evaluate_payload(payload)

        def serialize(self) -> dict[str, Any]:
            dag = cast(dict[str, Any], super().serialize())
            meta = dag.setdefault("meta", {})
            sr_meta = meta.setdefault("sr", {})
            sr_meta.update(
                {
                    "expression": self._expression,
                    "expression_key": self._expression_key,
                    "data_spec": self._data_spec,
                    "expression_dag_spec": self._expression_dag_spec,
                    "sr_engine": self._sr_engine,
                    **self._sr_metadata,
                }
            )
            return dag

    cname = strategy_name or f"sr_expr_{abs(hash(expression)) % 10000:04d}"
    ExpressionStrategy.__name__ = cname
    ExpressionStrategy.__qualname__ = cname
    return ExpressionStrategy


def build_strategy_from_dag_spec(
    dag_spec: Any,
    *,
    history_provider: Any | None,
    sr_engine: str | None = "pysr",
) -> type[Strategy]:
    """Create a Strategy from an ExpressionDagSpec-like object."""
    if history_provider is None:
        raise ValueError("history_provider (Seamless) is required for DAG-based strategies")

    expression = getattr(dag_spec, "equation", None) or getattr(dag_spec, "expression", "")
    data_spec = getattr(dag_spec, "data_spec", None)
    expression_key = getattr(dag_spec, "expression_key", None)

    dag_dict: dict[str, Any] | None = None
    if dataclass_asdict is not None and hasattr(dag_spec, "__dataclass_fields__"):
        try:  # pragma: no cover - defensive
            dag_dict = dataclass_asdict(dag_spec)
        except Exception:
            dag_dict = None
    dag_nodes = getattr(dag_spec, "nodes", None)
    dag_edges = getattr(dag_spec, "edges", None)

    data_spec_mapping = data_spec if isinstance(data_spec, Mapping) else {}
    interval = None
    period = None
    if isinstance(data_spec_mapping, Mapping):
        interval = data_spec_mapping.get("interval") or data_spec_mapping.get("timeframe")
        period = data_spec_mapping.get("period") or data_spec_mapping.get("min_history")

    class DagStrategy(Strategy):  # type: ignore[misc]
        _expression = expression
        _data_spec = data_spec_mapping or None
        _sr_engine = sr_engine
        _expression_key = expression_key or compute_expression_key(expression)
        _expression_dag_spec = dag_dict
        _sr_metadata = {
            "dag_node_count": getattr(dag_spec, "node_count", None),
            "dag_complexity": getattr(dag_spec, "complexity", None),
            "dag_loss": getattr(dag_spec, "loss", None),
            "spec_version": getattr(dag_spec, "spec_version", None),
        }

        def setup(self) -> None:  # pragma: no cover - runtime wiring
            if not _RUNTIME_AVAILABLE:
                # Fallback: keep metadata only
                return

            if not isinstance(dag_nodes, list) or not isinstance(dag_edges, list):
                raise ValueError("dag_spec must contain 'nodes' and 'edges'")

            id_to_spec = {n["id"]: n for n in dag_nodes if isinstance(n, Mapping)}
            indegree = {nid: 0 for nid in id_to_spec}
            for src, dst in dag_edges:
                if dst in indegree:
                    indegree[dst] += 1

            queue: deque[str] = deque([nid for nid, deg in indegree.items() if deg == 0])
            topo_order: list[str] = []
            while queue:
                nid = queue.popleft()
                topo_order.append(nid)
                for src, dst in dag_edges:
                    if src == nid:
                        indegree[dst] -= 1
                        if indegree[dst] == 0:
                            queue.append(dst)

            if len(topo_order) != len(id_to_spec):
                raise ValueError("dag_spec contains cycles or disconnected nodes")

            node_objs: dict[str, Any] = {}

            def _compute_stub(_: Any) -> Any:
                return None

            fingerprint = None
            if self._data_spec:
                ds = self._data_spec.get("dataset_id")
                snap = self._data_spec.get("snapshot_version") or self._data_spec.get("as_of")
                if ds and snap:
                    fingerprint = f"{ds}:{snap}"

            for nid in topo_order:
                spec = id_to_spec[nid]
                node_type = spec.get("node_type", "")
                label = spec.get("label") or node_type or nid
                params = spec.get("params") or {}
                inputs = spec.get("inputs") or []
                upstream = [node_objs[i] for i in inputs if i in node_objs]

                if node_type == "input":
                    node = StreamInput(
                        interval=interval or params.get("interval") or "60s",
                        period=period or params.get("period") or 200,
                        history_provider=history_provider,
                    )
                else:
                    tag = node_type.replace("/", "_") if node_type else "sr_node"
                    node = ProcessingNode(
                        upstream,
                        compute_fn=_compute_stub,
                        name=label,
                        interval=interval or params.get("interval"),
                        period=period or params.get("period"),
                        tags=["sr", tag],
                        config={"sr_node_type": node_type, "sr_params": params},
                    )
                if fingerprint:
                    try:
                        node.dataset_fingerprint = fingerprint
                    except Exception:
                        pass
                node_objs[nid] = node

            self.add_nodes(list(node_objs.values()))

        def serialize(self) -> dict[str, Any]:
            dag = super().serialize()
            meta = dag.setdefault("meta", {})
            sr_meta = meta.setdefault("sr", {})
            sr_meta.update(
                {
                    "expression": self._expression,
                    "expression_key": self._expression_key,
                    "data_spec": self._data_spec,
                    "expression_dag_spec": self._expression_dag_spec,
                    "sr_engine": self._sr_engine,
                }
            )
            sr_meta.update({k: v for k, v in self._sr_metadata.items() if v is not None})
            return dag

    if expression_key:
        cname = f"sr_dag_{expression_key[:8]}"
    else:
        cname = f"sr_dag_{abs(hash(expression)) % 10000:04d}"
    DagStrategy.__name__ = cname
    DagStrategy.__qualname__ = cname
    return DagStrategy
