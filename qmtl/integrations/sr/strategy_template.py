"""Strategy template builder for expression-based SR outputs.

This keeps SR 통합을 코어와 느슨하게 결합시키면서,
Seamless Data Provider와 동일 데이터를 사용하도록 Strategy를 생성한다.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
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


def _clean_dict(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (payload or {}).items() if v is not None}


def _build_sr_meta(
    *,
    expression: str,
    expression_key: str | None,
    data_spec: Mapping[str, Any] | None,
    expression_dag_spec: Mapping[str, Any] | None,
    sr_engine: str | None,
    spec_version: str,
    metadata: Mapping[str, Any] | None,
    on_duplicate: str | None,
) -> dict[str, Any]:
    resolved_spec_version = spec_version or "v1"
    clean_metadata = _clean_dict(metadata)

    try:
        key = compute_expression_key(expression, spec_version=resolved_spec_version)
    except Exception as exc:
        raise ValueError("expression_key is required and failed to compute") from exc

    if expression_key:
        key = expression_key
    if not key:
        raise ValueError("expression_key is required for SR submission")

    dedup_policy = {
        "expression_key": {
            "value": key,
            "spec_version": resolved_spec_version,
        }
    }
    dedup_on_duplicate = on_duplicate or clean_metadata.get("on_duplicate")
    if dedup_on_duplicate:
        dedup_policy["expression_key"]["on_duplicate"] = dedup_on_duplicate

    clean_metadata.pop("on_duplicate", None)
    clean_metadata.pop("spec_version", None)
    clean_metadata.pop("expression_key", None)

    sr_meta = {
        "expression": expression,
        "expression_key": key,
        "spec_version": resolved_spec_version,
        "expression_key_meta": {
            "value": key,
            "spec_version": resolved_spec_version,
        },
        "data_spec": dict(data_spec) if isinstance(data_spec, Mapping) else None,
        "expression_dag_spec": dict(expression_dag_spec) if isinstance(expression_dag_spec, Mapping) else None,
        "sr_engine": sr_engine,
        "dedup_policy": dedup_policy,
        **clean_metadata,
    }

    return _clean_dict(sr_meta)


@dataclass(frozen=True)
class ValidationPoint:
    input: Mapping[str, Any]
    expected: float | int | None


@dataclass
class ValidationSample:
    points: list[ValidationPoint]
    epsilon_abs: float = 0.0
    epsilon_rel: float = 0.0

    @classmethod
    def parse(cls, payload: Any) -> "ValidationSample":
        if payload is None:
            raise ValueError("validation_sample payload is required")

        epsilon_section = payload.get("epsilon", {}) if isinstance(payload, Mapping) else {}
        epsilon_abs_raw = payload.get("epsilon_abs") if isinstance(payload, Mapping) else None
        epsilon_rel_raw = payload.get("epsilon_rel") if isinstance(payload, Mapping) else None
        epsilon_abs = (
            _to_float(epsilon_abs_raw, 0.0) if epsilon_abs_raw is not None else _to_float(epsilon_section.get("abs"), 0.0)
        )
        epsilon_rel = (
            _to_float(epsilon_rel_raw, 0.0) if epsilon_rel_raw is not None else _to_float(epsilon_section.get("rel"), 0.0)
        )

        if isinstance(payload, Mapping):
            points_payload = payload.get("points") or payload.get("samples")
        else:
            points_payload = payload

        points = _parse_points(points_payload)
        return cls(points=points, epsilon_abs=epsilon_abs, epsilon_rel=epsilon_rel)


@dataclass(frozen=True)
class ValidationMismatch:
    index: int
    expected: float | int | None
    actual: float | None
    abs_error: float | None
    rel_error: float | None
    input: Mapping[str, Any]


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    mismatches: list[ValidationMismatch]


class ValidationSampleMismatch(ValueError):
    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        details = "; ".join(
            [
                f"#{m.index}: expected={m.expected}, actual={m.actual}, abs_err={m.abs_error}, rel_err={m.rel_error}"
                for m in result.mismatches
            ]
        )
        super().__init__(f"validation_sample mismatch ({details})")


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_points(points_payload: Any) -> list[ValidationPoint]:
    if points_payload is None:
        raise ValueError("validation_sample requires 'points' or a list payload")

    if not isinstance(points_payload, Sequence) or isinstance(points_payload, (str, bytes, bytearray)):
        raise ValueError("validation_sample points must be a sequence of samples")

    parsed: list[ValidationPoint] = []
    for raw in points_payload:
        parsed.append(_parse_point(raw))

    if not parsed:
        raise ValueError("validation_sample requires at least one point")
    return parsed


def _parse_point(raw: Any) -> ValidationPoint:
    if isinstance(raw, Mapping):
        input_payload, expected = _parse_point_mapping(raw)
    elif isinstance(raw, (tuple, list)) and len(raw) == 2:
        input_payload, expected = _parse_point_tuple(raw)
    else:
        raise ValueError("validation_sample points must be mappings or (mapping, expected) tuples")

    return ValidationPoint(
        input=cast(Mapping[str, Any], input_payload),
        expected=cast(float | int | None, expected),
    )


def _parse_point_mapping(raw: Mapping[str, Any]) -> tuple[Mapping[str, Any], Any]:
    input_payload = raw.get("input") or raw.get("inputs")
    expected = raw.get("expected")
    if expected is None:
        expected = raw.get("output", raw.get("value"))

    if input_payload is None:
        known_keys = {"expected", "output", "value", "input", "inputs"}
        leftovers = {k: v for k, v in raw.items() if k not in known_keys}
        if leftovers:
            input_payload = leftovers

    if not isinstance(input_payload, Mapping):
        raise ValueError("Each validation sample must include an 'input' mapping")
    return input_payload, expected


def _parse_point_tuple(raw: Sequence[Any]) -> tuple[Mapping[str, Any], Any]:
    input_payload, expected = raw
    if not isinstance(input_payload, Mapping):
        raise ValueError("Tuple validation samples must be (mapping, expected)")
    return input_payload, expected


def _within_tolerance(expected: float, actual: float, *, epsilon_abs: float, epsilon_rel: float) -> tuple[bool, float, float]:
    abs_error = abs(actual - expected)
    rel_error = abs_error / max(abs(expected), 1e-12)
    return abs_error <= epsilon_abs or rel_error <= epsilon_rel, abs_error, rel_error


def validate_strategy_against_sample(
    strategy_cls: type["Strategy"],
    validation_sample: ValidationSample | Mapping[str, Any] | Sequence[Any],
    *,
    epsilon_abs: float | None = None,
    epsilon_rel: float | None = None,
) -> ValidationResult:
    sample = validation_sample if isinstance(validation_sample, ValidationSample) else ValidationSample.parse(validation_sample)
    if epsilon_abs is not None:
        sample = replace(sample, epsilon_abs=epsilon_abs)
    if epsilon_rel is not None:
        sample = replace(sample, epsilon_rel=epsilon_rel)

    strategy = strategy_cls()
    evaluator = getattr(strategy, "evaluate", None)
    if not callable(evaluator):
        raise ValueError("strategy_cls must expose an evaluate(payload) helper for validation")

    mismatches: list[ValidationMismatch] = []
    for idx, point in enumerate(sample.points):
        actual = evaluator(point.input)
        if actual is None or point.expected is None:
            mismatches.append(
                ValidationMismatch(
                    index=idx,
                    expected=point.expected,
                    actual=cast(float | None, actual),
                    abs_error=None,
                    rel_error=None,
                    input=point.input,
                )
            )
            continue

        within, abs_error, rel_error = _within_tolerance(
            float(point.expected), float(actual),
            epsilon_abs=sample.epsilon_abs,
            epsilon_rel=sample.epsilon_rel,
        )
        if not within:
            mismatches.append(
                ValidationMismatch(
                    index=idx,
                    expected=point.expected,
                    actual=float(actual),
                    abs_error=abs_error,
                    rel_error=rel_error,
                    input=point.input,
                )
            )

    return ValidationResult(passed=not mismatches, mismatches=mismatches)


def submit_with_validation(
    strategy_cls: type["Strategy"],
    *,
    validation_sample: ValidationSample | Mapping[str, Any] | Sequence[Any] | None = None,
    epsilon_abs: float | None = None,
    epsilon_rel: float | None = None,
    submit_fn: Callable[..., Any] | None = None,
    **submit_kwargs: Any,
) -> Any:
    if validation_sample is not None:
        result = validate_strategy_against_sample(
            strategy_cls,
            validation_sample,
            epsilon_abs=epsilon_abs,
            epsilon_rel=epsilon_rel,
        )
        if not result.passed:
            raise ValidationSampleMismatch(result)

    submit_callable = submit_fn
    if submit_callable is None:
        from qmtl.runtime.sdk import Runner

        submit_callable = Runner.submit

    return submit_callable(strategy_cls, **submit_kwargs)


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
    spec_version: str = "v1",
    on_duplicate: str | None = "replace",
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
        spec_version : str, optional
            Expression spec version tagged alongside the expression_key (default: "v1").
        on_duplicate : str, optional
            Deduplication policy for World/Gateway ("replace" or "reject").
    """
    parsed, symbols, fn = _compile_expression(expression)
    sr_meta = _build_sr_meta(
        expression=expression,
        expression_key=expression_key,
        data_spec=data_spec,
        expression_dag_spec=expression_dag_spec,
        sr_engine=sr_engine,
        spec_version=spec_version,
        metadata=metadata,
        on_duplicate=on_duplicate,
    )
    expr_key = sr_meta["expression_key"]
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
        _expression_dag_spec = sr_meta.get("expression_dag_spec")
        _sr_metadata = sr_meta

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
            sr_meta.update(self._sr_metadata)
            return dag

    cname = strategy_name or f"sr_expr_{abs(hash(expression)) % 10000:04d}"
    ExpressionStrategy.__name__ = cname
    ExpressionStrategy.__qualname__ = cname
    return ExpressionStrategy


def _extract_dag_fields(
    dag_spec: Any,
) -> tuple[str, Any, Mapping[str, Any], Any, Any, dict[str, Any] | None, Any, Any]:
    expression = getattr(dag_spec, "equation", None) or getattr(dag_spec, "expression", "")
    expression_key = getattr(dag_spec, "expression_key", None)
    data_spec_mapping = _coerce_mapping(getattr(dag_spec, "data_spec", None))
    interval, period = _extract_interval_period(data_spec_mapping)
    dag_dict = _maybe_dataclass_asdict(dag_spec)
    dag_nodes = getattr(dag_spec, "nodes", None)
    dag_edges = getattr(dag_spec, "edges", None)
    expr_str = expression or ""
    return expr_str, expression_key, data_spec_mapping, interval, period, dag_dict, dag_nodes, dag_edges


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _extract_interval_period(data_spec_mapping: Mapping[str, Any]) -> tuple[Any, Any]:
    interval = data_spec_mapping.get("interval") or data_spec_mapping.get("timeframe")
    period = data_spec_mapping.get("period") or data_spec_mapping.get("min_history")
    return interval, period


def _maybe_dataclass_asdict(dag_spec: Any) -> dict[str, Any] | None:
    if dataclass_asdict is None or not hasattr(dag_spec, "__dataclass_fields__"):
        return None
    try:  # pragma: no cover - defensive
        return dataclass_asdict(dag_spec)
    except Exception:
        return None


def build_strategy_from_dag_spec(
    dag_spec: Any,
    *,
    history_provider: Any | None,
    sr_engine: str | None = "pysr",
    spec_version: str | None = None,
    on_duplicate: str | None = "replace",
) -> type[Strategy]:
    """Create a Strategy from an ExpressionDagSpec-like object."""
    if history_provider is None:
        raise ValueError("history_provider (Seamless) is required for DAG-based strategies")

    (
        expr_str,
        expression_key,
        data_spec_mapping,
        interval,
        period,
        dag_dict,
        dag_nodes,
        dag_edges,
    ) = _extract_dag_fields(dag_spec)

    resolved_spec_version = spec_version or getattr(dag_spec, "spec_version", None) or "v1"
    sr_meta = _build_sr_meta(
        expression=expr_str,
        expression_key=expression_key,
        data_spec=data_spec_mapping,
        expression_dag_spec=dag_dict,
        sr_engine=sr_engine,
        spec_version=resolved_spec_version,
        metadata={
            "dag_node_count": getattr(dag_spec, "node_count", None),
            "dag_complexity": getattr(dag_spec, "complexity", None),
            "dag_loss": getattr(dag_spec, "loss", None),
            "spec_version": getattr(dag_spec, "spec_version", None),
        },
        on_duplicate=on_duplicate,
    )

    class DagStrategy(Strategy):
        _expression = expr_str
        _data_spec = data_spec_mapping or None
        _sr_engine = sr_engine
        _expression_key = sr_meta["expression_key"]
        _expression_dag_spec = sr_meta.get("expression_dag_spec")
        _compiled = _compile_expression(expr_str)
        _sr_metadata = sr_meta

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
            return self._evaluate_payload(payload)

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

            def _make_compute(node_type: str, params: Mapping[str, Any] | None, upstream_objs: list[Any]):
                def _extract_from_stream(view: Any, stream: StreamInput) -> tuple[Any, Any] | tuple[None, None]:
                    try:
                        window = view[stream.node_id][stream.interval]
                        latest = window.latest()
                        rows = getattr(window, "_data", None)
                    except Exception:
                        return None, None
                    ts = None
                    payload = latest
                    try:
                        from collections.abc import Sequence as _Seq

                        if isinstance(rows, _Seq) and rows:
                            ts, payload = rows[-1]
                    except Exception:
                        pass
                    return ts, payload

                def _extract_value(view: Any, upstream: Any) -> tuple[Any, Any] | tuple[None, None]:
                    if isinstance(upstream, StreamInput):
                        return _extract_from_stream(view, upstream)
                    try:
                        result = view[upstream.node_id]
                    except Exception:
                        return None, None
                    if isinstance(result, Mapping):
                        ts = result.get("ts")
                        if "signal" in result:
                            return ts, result.get("signal")
                        if "value" in result:
                            return ts, result.get("value")
                    return None, None

                def _compute(view: Any) -> Any:
                    import math

                    values: list[Any] = []
                    ts = None
                    for upstream in upstream_objs:
                        uts, val = _extract_value(view, upstream)
                        if ts is None:
                            ts = uts
                        values.append(val)
                    if not values or any(v is None for v in values):
                        return None

                    try:
                        if node_type == "math/add":
                            out = sum(values)
                        elif node_type == "math/mul":
                            out = math.prod(values)
                        elif node_type == "math/pow" and len(values) >= 2:
                            out = math.pow(values[0], values[1])
                        elif node_type == "math/abs":
                            out = abs(values[0])
                        elif node_type == "math/sin":
                            out = math.sin(values[0])
                        elif node_type == "math/cos":
                            out = math.cos(values[0])
                        elif node_type == "math/exp":
                            out = math.exp(values[0])
                        elif node_type == "math/log":
                            out = math.log(values[0])
                        elif node_type == "logic/and":
                            out = all(values)
                        elif node_type == "logic/or":
                            out = any(values)
                        elif node_type == "logic/not":
                            out = not values[0]
                        elif node_type == "cmp/gte" and len(values) >= 2:
                            out = values[0] >= values[1]
                        elif node_type == "cmp/gt" and len(values) >= 2:
                            out = values[0] > values[1]
                        elif node_type == "cmp/lte" and len(values) >= 2:
                            out = values[0] <= values[1]
                        elif node_type == "cmp/lt" and len(values) >= 2:
                            out = values[0] < values[1]
                        elif node_type == "cmp/eq" and len(values) >= 2:
                            out = values[0] == values[1]
                        elif node_type == "cmp/ne" and len(values) >= 2:
                            out = values[0] != values[1]
                        else:
                            # Default passthrough for unrecognized nodes
                            out = values[0]
                    except Exception:
                        return None

                    return {"ts": ts, "value": out, "signal": out}

                return _compute

            fingerprint = None
            if self._data_spec:
                ds = self._data_spec.get("dataset_id")
                snap = self._data_spec.get("snapshot_version") or self._data_spec.get("as_of")
                if ds and snap:
                    fingerprint = f"{ds}:{snap}"

            node: Any
            for nid in topo_order:
                spec = id_to_spec[nid]
                node_type = spec.get("node_type", "")
                label = spec.get("label") or node_type or nid
                params = spec.get("params") or {}
                inputs = spec.get("inputs") or []
                upstream = [node_objs[i] for i in inputs if i in node_objs]
                if not upstream:
                    upstream = [
                        node_objs[src]
                        for src, dst in dag_edges
                        if dst == nid and src in node_objs
                    ]

                if node_type == "input":
                    node = StreamInput(
                        interval=interval or params.get("interval") or "60s",
                        period=period or params.get("period") or 200,
                        history_provider=history_provider,
                    )
                else:
                    tag = node_type.replace("/", "_") if node_type else "sr_node"
                    if not upstream:
                        raise ValueError(f"processing node {nid} has no upstream inputs")
                    compute_fn = _make_compute(node_type, params, upstream)
                    node = ProcessingNode(
                        upstream,
                        compute_fn=compute_fn,
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
            dag = cast(dict[str, Any], super().serialize())
            meta = dag.setdefault("meta", {})
            sr_meta = meta.setdefault("sr", {})
            sr_meta.update(self._sr_metadata)
            return dag

    cname = f"sr_dag_{sr_meta['expression_key'][:8]}"
    DagStrategy.__name__ = cname
    DagStrategy.__qualname__ = cname
    return DagStrategy
