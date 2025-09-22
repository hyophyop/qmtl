from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any
import logging
import time

from opentelemetry import trace

try:  # Optional pandas dependency
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover - pandas not installed
    pd = None  # type: ignore

from qmtl.common import CanonicalNodeSpec, compute_node_id
from qmtl.common.compute_key import (
    ComputeContext,
    compute_compute_key,
    DEFAULT_EXECUTION_DOMAIN,
)

from .. import arrow_cache
from .. import metrics as sdk_metrics
from .. import node_validation as default_validator
from .. import hash_utils as default_hash_utils
from ..cache import NodeCache
from ..event_service import EventRecorderService
from ..exceptions import NodeValidationError
from ..util import parse_interval


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _extract_schema_compat_id(schema: Any, expected_schema: Any) -> str | None:
    """Extract a schema compatibility identifier from provided schemas."""

    compat_id: Any = None
    if isinstance(schema, dict):
        compat_id = (
            schema.get("schema_compat_id")
            or schema.get("compat_id")
            or schema.get("compatId")
        )
    if compat_id is None and isinstance(expected_schema, dict):
        compat_id = (
            expected_schema.get("schema_compat_id")
            or expected_schema.get("compat_id")
            or expected_schema.get("compatId")
        )
    if compat_id is None:
        return None
    return str(compat_id)


class Node:
    """Represents a processing node in a strategy DAG.

    ``compute_fn`` must accept exactly **one argument** – a :class:`CacheView`
    returned by :py:meth:`NodeCache.view`. The view provides read-only access to
    the cached data and mirrors the structure returned by
    :py:meth:`NodeCache.view`. Positional arguments other than the cache view are
    **not** supported. ``input`` may be a single ``Node`` or an iterable of
    ``Node`` instances. Passing dictionaries is no longer supported. Tags can be
    assigned at initialization or later via :py:meth:`add_tag`.
    """

    def __init__(
        self,
        input: "Node" | Iterable["Node"] | None = None,
        compute_fn=None,
        name: str | None = None,
        interval: int | str | None = None,
        period: int | None = None,
        tags: list[str] | None = None,
        config: dict | None = None,
        schema: dict | None = None,
        expected_schema: dict | None = None,
        *,
        allowed_lateness: int = 0,
        on_late: str = "recompute",
        runtime_compat: str = "loose",
        validator=default_validator,
        hash_utils=default_hash_utils,
        event_service: EventRecorderService | None = None,
    ) -> None:
        self.validator = validator
        self.hash_utils = hash_utils
        self.event_service = event_service

        if isinstance(interval, str):
            interval = parse_interval(interval)

        validator.validate_compute_fn(compute_fn)
        (
            validated_name,
            validated_tags,
            interval_val,
            period_val,
        ) = validator.validate_node_params(
            name,
            tags,
            interval,
            period,
            config,
            schema,
            expected_schema,
        )

        if isinstance(interval_val, str):
            interval_val = parse_interval(interval_val)

        self.input = input
        self.inputs = validator.normalize_inputs(input)
        self.compute_fn = compute_fn
        self.name = validated_name
        self.interval = interval_val
        self.period = period_val
        self.tags = validated_tags
        self.config = config or {}
        self.schema = schema or {}
        self.expected_schema = expected_schema or {}
        self.execute = True
        self.kafka_topic: str | None = None
        self.enable_feature_artifacts = bool(
            self.config.get("enable_feature_artifacts", False)
        )
        self.schema_compat_id: str = (
            _extract_schema_compat_id(self.schema, self.expected_schema)
            or self.schema_hash
        )
        if arrow_cache.ARROW_AVAILABLE and os.getenv("QMTL_ARROW_CACHE") == "1":
            self.cache = arrow_cache.NodeCacheArrow(period_val or 0)
        else:
            self.cache = NodeCache(period_val or 0)
        self.pre_warmup = True
        self._warmup_started_at = time.perf_counter()
        self.allowed_lateness: int = int(allowed_lateness)
        self.on_late: str = on_late
        self._last_watermark: int | None = None
        self._late_events: list[tuple[str, int, Any]] = []
        self.runtime_compat: str = runtime_compat
        self._compute_context = ComputeContext()
        self._dataset_fingerprint: str | None = None
        self.cache.activate_compute_key(
            self.compute_key,
            node_id=self.node_id,
            world_id=self._compute_context.world_id,
            execution_domain=self._compute_context.execution_domain,
            as_of=self._compute_context.as_of,
            partition=self._compute_context.partition,
        )

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return (
            f"Node(name={self.name!r}, interval={self.interval}, period={self.period})"
        )

    def add_tag(self, tag: str) -> "Node":
        """Append ``tag`` to :attr:`tags` if missing and return ``self``."""

        validated_tag = self.validator.validate_tag(tag)
        if validated_tag not in self.tags:
            self.tags.append(validated_tag)
        return self

    def _canonical_spec(self) -> CanonicalNodeSpec:
        deps = [n.node_id for n in self.inputs]
        return (
            CanonicalNodeSpec()
            .with_node_type(self.node_type)
            .with_interval(self.interval)
            .with_period(self.period)
            .with_params(self.config)
            .with_dependencies(deps)
            .with_schema_compat_id(self.schema_compat_id)
            .with_code_hash(self.code_hash)
            .update_extras(
                {
                    "name": self.name,
                    "tags": list(self.tags),
                    "inputs": list(deps),
                    "config_hash": self.config_hash,
                    "schema_hash": self.schema_hash,
                    "pre_warmup": self.pre_warmup,
                    "expected_schema": self.expected_schema,
                }
            )
        )

    @property
    def node_type(self) -> str:
        return self.__class__.__name__

    @property
    def code_hash(self) -> str:
        return self.hash_utils.code_hash(self.compute_fn)

    @property
    def config_hash(self) -> str:
        return self.hash_utils.config_hash(self.config)

    @property
    def schema_hash(self) -> str:
        return self.hash_utils.schema_hash(self.schema)

    @property
    def node_id(self) -> str:
        return compute_node_id(self._canonical_spec())

    @property
    def node_hash(self) -> str:
        return self.node_id

    @property
    def compute_context(self) -> ComputeContext:
        return self._compute_context

    @property
    def compute_key(self) -> str:
        return compute_compute_key(self.node_hash, self._compute_context)

    def apply_compute_context(self, context: ComputeContext) -> None:
        if context == self._compute_context:
            return
        self._compute_context = context
        self.pre_warmup = True
        self._warmup_started_at = time.perf_counter()
        self.cache.activate_compute_key(
            self.compute_key,
            node_id=self.node_id,
            world_id=context.world_id,
            execution_domain=context.execution_domain,
            as_of=context.as_of,
            partition=context.partition,
        )

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
    def dataset_fingerprint(self) -> str | None:
        return self._dataset_fingerprint

    @dataset_fingerprint.setter
    def dataset_fingerprint(self, value: str | None) -> None:
        self._dataset_fingerprint = value or None

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
            and pd is not None
            and isinstance(payload, pd.DataFrame)
            and mode != "off"
        ):
            from ..schema_validation import validate_schema

            try:
                validate_schema(payload, self.expected_schema)
            except NodeValidationError as e:
                msg = f"{self.name or self.node_id}: {e}"
                if mode == "warn":
                    logger.warning(msg)
                elif mode == "fail":
                    raise NodeValidationError(msg) from e

        with tracer.start_as_current_span(
            "node.feed", attributes={"node.id": self.node_id}
        ):
            self.cache.activate_compute_key(
                self.compute_key,
                node_id=self.node_id,
                world_id=self._compute_context.world_id,
                execution_domain=self._compute_context.execution_domain,
                as_of=self._compute_context.as_of,
                partition=self._compute_context.partition,
            )
            self.cache.append(upstream_id, interval, timestamp, payload)
            sdk_metrics.observe_nodecache_resident_bytes(
                self.node_id, self.cache.resident_bytes
            )

        if self.event_service is not None:
            self.event_service.record(self.node_id, interval, timestamp, payload)

        if self.pre_warmup and self.cache.ready():
            self.pre_warmup = False
            try:
                duration_ms = (
                    time.perf_counter() - self._warmup_started_at
                ) * 1000.0
                sdk_metrics.observe_warmup_ready(self.node_id, duration_ms)
            except Exception:
                pass

        missing = self.cache.missing_flags().get(upstream_id, {}).get(interval, False)
        if missing:
            if on_missing == "fail":
                raise RuntimeError("gap detected")
            if on_missing == "skip":
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
        wm = int(self._last_watermark)

        if bucket_ts < wm:
            policy = (self.on_late or "recompute").lower()
            if policy == "ignore":
                return False
            if policy == "side_output":
                self._late_events.append((upstream_id, bucket_ts, payload))
                return False
            return True

        if bucket_ts >= wm:
            return True

        return False

    def watermark(self) -> int | None:
        return self._last_watermark

    def to_dict(self) -> dict:
        spec = self._canonical_spec()
        payload = spec.to_payload()
        payload["node_id"] = compute_node_id(spec)
        return payload


__all__ = ["Node"]

