from __future__ import annotations

import logging
import time
from typing import Any

from opentelemetry import trace

from qmtl.foundation.common.compute_key import ComputeContext, DEFAULT_EXECUTION_DOMAIN

from .. import metrics as sdk_metrics
from ..exceptions import NodeValidationError


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class CacheActivationMixin:
    """Utility mixin that knows how to activate a node cache."""

    cache: Any
    node_id: str
    _compute_context: ComputeContext
    compute_key: Any

    def _activate_cache_key(self) -> None:
        self.cache.activate_compute_key(
            self.compute_key,
            node_id=self.node_id,
            world_id=self._compute_context.world_id,
            execution_domain=self._compute_context.execution_domain,
            as_of=self._compute_context.as_of,
            partition=self._compute_context.partition,
        )


class ComputeContextMixin(CacheActivationMixin):
    """Manage :class:`ComputeContext` lifecycle and convenience accessors."""

    pre_warmup: bool
    _warmup_started_at: float

    def _setup_compute_context(self) -> None:
        self._compute_context = ComputeContext()
        self._reset_warmup_timer()

    def _reset_warmup_timer(self) -> None:
        self.pre_warmup = True
        self._warmup_started_at = time.perf_counter()

    @property
    def compute_context(self) -> ComputeContext:
        return self._compute_context

    def apply_compute_context(self, context: ComputeContext) -> None:
        if context == self._compute_context:
            return
        self._compute_context = context
        self._reset_warmup_timer()
        self._activate_cache_key()

    @property
    def world_id(self) -> str | None:
        val = self._compute_context.world_id
        return val or None

    @world_id.setter
    def world_id(self, value: str | None) -> None:
        context = ComputeContext(
            world_id=str(value or ""),
            execution_domain=self._compute_context.execution_domain,
            as_of=self._compute_context.as_of,
            partition=self._compute_context.partition,
        )
        self.apply_compute_context(context)

    @property
    def execution_domain(self) -> str:
        return self._compute_context.execution_domain

    @execution_domain.setter
    def execution_domain(self, value: str) -> None:
        context = ComputeContext(
            world_id=self._compute_context.world_id,
            execution_domain=str(value or DEFAULT_EXECUTION_DOMAIN),
            as_of=self._compute_context.as_of,
            partition=self._compute_context.partition,
        )
        self.apply_compute_context(context)

    @property
    def as_of(self) -> Any | None:
        return self._compute_context.as_of

    @as_of.setter
    def as_of(self, value: Any | None) -> None:
        context = ComputeContext(
            world_id=self._compute_context.world_id,
            execution_domain=self._compute_context.execution_domain,
            as_of=value,
            partition=self._compute_context.partition,
        )
        self.apply_compute_context(context)

    @property
    def partition(self) -> Any | None:
        return self._compute_context.partition

    @partition.setter
    def partition(self, value: Any | None) -> None:
        context = ComputeContext(
            world_id=self._compute_context.world_id,
            execution_domain=self._compute_context.execution_domain,
            as_of=self._compute_context.as_of,
            partition=value,
        )
        self.apply_compute_context(context)


class LateEventPolicy:
    """Encapsulate how late arrivals should be treated."""

    def __init__(self, mode: str, sink: list[tuple[str, int, Any]]) -> None:
        self._mode = (mode or "recompute").lower()
        self._sink = sink

    def should_process(
        self,
        upstream_id: str,
        bucket_ts: int,
        watermark: int,
        payload: Any,
    ) -> bool:
        if bucket_ts < watermark:
            if self._mode == "ignore":
                return False
            if self._mode == "side_output":
                self._sink.append((upstream_id, bucket_ts, payload))
                return False
            return True
        if bucket_ts >= watermark:
            return True
        return False


class NodeFeedMixin(CacheActivationMixin):
    """Provide the :py:meth:`Node.feed` implementation."""

    validator: Any
    compute_fn: Any
    expected_schema: dict[str, Any]
    event_service: Any
    pre_warmup: bool
    _warmup_started_at: float
    _last_watermark: int | None
    allowed_lateness: int
    cache: Any
    _late_events: list[tuple[str, int, Any]]
    name: str | None
    on_late: str

    def feed(
        self,
        upstream_id: str,
        interval: int,
        timestamp: int,
        payload,
        *,
        on_missing: str = "skip",
    ) -> bool:
        from ..node_validation import validate_feed_params

        validate_feed_params(upstream_id, interval, timestamp, on_missing)

        mode = getattr(self, "_schema_enforcement", "fail").lower()
        if (
            self.expected_schema
            and self._should_validate_schema(payload)
            and mode != "off"
        ):
            from ..schema_validation import validate_schema

            try:
                validate_schema(payload, self.expected_schema)
            except NodeValidationError as exc:
                msg = f"{self.name or self.node_id}: {exc}"
                if mode == "warn":
                    logger.warning(msg)
                elif mode == "fail":
                    raise NodeValidationError(msg) from exc

        with tracer.start_as_current_span(
            "node.feed", attributes={"node.id": self.node_id}
        ):
            self._activate_cache_key()
            self.cache.append(upstream_id, interval, timestamp, payload)
            self._record_resident_bytes()

        if self.event_service is not None:
            self.event_service.record(self.node_id, interval, timestamp, payload)

        self._maybe_record_warmup_ready()

        if self._is_missing(upstream_id, interval, on_missing):
            return False

        try:
            self._last_watermark = self.cache.watermark(
                allowed_lateness=self.allowed_lateness
            )
        except Exception:
            self._last_watermark = None

        if self.pre_warmup or self.compute_fn is None:
            return False

        if self._last_watermark is None:
            return False

        bucket_ts = timestamp - (timestamp % (interval or 1))
        watermark = int(self._last_watermark)
        policy = LateEventPolicy(self.on_late, self._late_events)
        return policy.should_process(upstream_id, bucket_ts, watermark, payload)

    def _should_validate_schema(self, payload: Any) -> bool:
        try:  # Optional pandas dependency
            import pandas as pd
        except Exception:  # pragma: no cover - pandas not installed
            return False

        return isinstance(payload, pd.DataFrame)

    def _record_resident_bytes(self) -> None:
        if hasattr(self.cache, "record_resident_bytes"):
            self.cache.record_resident_bytes(self.node_id)
        else:
            sdk_metrics.observe_nodecache_resident_bytes(
                self.node_id, self.cache.resident_bytes
            )

    def _maybe_record_warmup_ready(self) -> None:
        if self.pre_warmup and self.cache.ready():
            self.pre_warmup = False
            try:
                duration_ms = (
                    time.perf_counter() - self._warmup_started_at
                ) * 1000.0
                sdk_metrics.observe_warmup_ready(self.node_id, duration_ms)
            except Exception:
                pass

    def _is_missing(
        self, upstream_id: str, interval: int, on_missing: str
    ) -> bool:
        missing = (
            self.cache.missing_flags().get(upstream_id, {}).get(interval, False)
        )
        if missing:
            if on_missing == "fail":
                raise RuntimeError("gap detected")
            if on_missing == "skip":
                return True
        return False


__all__ = [
    "CacheActivationMixin",
    "ComputeContextMixin",
    "LateEventPolicy",
    "NodeFeedMixin",
]
