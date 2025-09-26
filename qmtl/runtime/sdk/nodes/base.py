from __future__ import annotations

import os
from typing import Any, Iterable

from qmtl.foundation.common import CanonicalNodeSpec, compute_node_id
from qmtl.foundation.common.compute_key import compute_compute_key

from .. import arrow_cache
from ..cache import NodeCache
from ..event_service import EventRecorderService
from .config import NodeConfig
from .mixins import ComputeContextMixin, NodeFeedMixin


_UNSET = object()


class Node(ComputeContextMixin, NodeFeedMixin):
    """Represents a processing node in a strategy DAG."""

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
        validator: Any = None,
        hash_utils: Any = None,
        event_service: EventRecorderService | None = None,
    ) -> None:
        from .. import node_validation as default_validator
        from .. import hash_utils as default_hash_utils

        self.validator = validator or default_validator
        self.hash_utils = hash_utils or default_hash_utils
        self.event_service = event_service

        config_payload = NodeConfig.build(
            input=input,
            compute_fn=compute_fn,
            name=name,
            tags=tags,
            interval=interval,
            period=period,
            config=config,
            schema=schema,
            expected_schema=expected_schema,
            allowed_lateness=allowed_lateness,
            on_late=on_late,
            runtime_compat=runtime_compat,
            validator=self.validator,
            hash_utils=self.hash_utils,
        )

        self.input = input
        self.inputs = config_payload.inputs
        self.compute_fn = compute_fn
        self.name = config_payload.name
        self.interval = config_payload.interval
        self.period = config_payload.period
        self.tags = config_payload.tags
        self.config = config_payload.config
        self.schema = config_payload.schema
        self.expected_schema = config_payload.expected_schema
        self.execute = True
        self.kafka_topic: str | None = None
        self.enable_feature_artifacts = config_payload.enable_feature_artifacts
        self.schema_compat_id = config_payload.schema_compat_id
        self.runtime_compat: str = config_payload.runtime_compat
        self.allowed_lateness: int = config_payload.allowed_lateness
        self.on_late: str = config_payload.on_late

        self.cache = self._create_cache(config_payload.period)
        self._setup_compute_context()
        self._activate_cache_key()

        self._last_watermark: int | None = None
        self._late_events: list[tuple[str, int, Any]] = []
        self._dataset_fingerprint: str | None = None
        self._last_fetch_metadata: Any | None = None

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return (
            f"Node(name={self.name!r}, interval={self.interval}, period={self.period})"
        )

    def _create_cache(self, period: int | None) -> Any:
        if arrow_cache.ARROW_AVAILABLE and os.getenv("QMTL_ARROW_CACHE") == "1":
            return arrow_cache.NodeCacheArrow(period or 0)
        return NodeCache(period or 0)

    def add_tag(self, tag: str) -> "Node":
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
    def compute_key(self) -> str:
        return compute_compute_key(self.node_hash, self._compute_context)

    @property
    def dataset_fingerprint(self) -> str | None:
        return self._dataset_fingerprint

    @dataset_fingerprint.setter
    def dataset_fingerprint(self, value: str | None) -> None:
        self.update_compute_context(dataset_fingerprint=value)

    @property
    def last_fetch_metadata(self) -> Any | None:
        return self._last_fetch_metadata

    @last_fetch_metadata.setter
    def last_fetch_metadata(self, value: Any | None) -> None:
        self._last_fetch_metadata = value

    def update_compute_context(
        self,
        *,
        execution_domain: Any = _UNSET,
        as_of: Any = _UNSET,
        partition: Any = _UNSET,
        dataset_fingerprint: Any = _UNSET,
    ) -> None:
        overrides: dict[str, Any] = {}
        if execution_domain is not _UNSET:
            overrides["execution_domain"] = execution_domain
        if as_of is not _UNSET:
            overrides["as_of"] = as_of
        if partition is not _UNSET:
            overrides["partition"] = partition
        if dataset_fingerprint is not _UNSET:
            overrides["dataset_fingerprint"] = dataset_fingerprint
        if not overrides:
            return

        new_context = self._compute_context.with_overrides(**overrides)
        if new_context != self._compute_context:
            self._compute_context = new_context
            self._activate_cache_key()

        if dataset_fingerprint is not _UNSET:
            self._dataset_fingerprint = dataset_fingerprint or None

    def watermark(self) -> int | None:
        return self._last_watermark

    def to_dict(self) -> dict:
        spec = self._canonical_spec()
        payload = spec.to_payload()
        payload["node_id"] = compute_node_id(spec)
        return payload


__all__ = ["Node"]
