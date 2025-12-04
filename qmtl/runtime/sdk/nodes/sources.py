from __future__ import annotations

import logging
from typing import cast

from qmtl.foundation.common.tagquery import (
    MatchMode,
    canonical_tag_query_params,
    normalize_match_mode,
)

from .. import hash_utils as default_hash_utils
from .. import node_validation as default_validator
from ..event_service import EventRecorderService
from ..exceptions import InvalidParameterError
from ..data_io import HistoryBackend, HistoryProvider, EventRecorder
from ..util import parse_interval
from .base import Node


logger = logging.getLogger(__name__)

__all__ = ["SourceNode", "StreamInput", "TagQueryNode"]


class SourceNode(Node):
    """Base class for nodes without upstream dependencies."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("input", None)
        super().__init__(*args, **kwargs)


class StreamInput(SourceNode):
    """Represents an upstream data stream placeholder.

    ``history_provider`` and ``event_service`` must be supplied when the
    instance is created. These dependencies are immutable for the lifetime of
    the node. Only the :class:`EventRecorderService` path is supported for
    event recording.
    """

    def __init__(
        self,
        tags: list[str] | None = None,
        interval: int | str | None = None,
        period: int | None = None,
        *,
        history_provider: HistoryProvider | HistoryBackend | object | None = None,
        event_service: EventRecorderService | None = None,
        validator=default_validator,
        hash_utils=default_hash_utils,
        **node_kwargs,
    ) -> None:
        self._allow_event_service_set = True
        super().__init__(
            input=None,
            compute_fn=None,
            name="stream_input",
            interval=interval,
            period=period,
            tags=tags or [],
            validator=validator,
            hash_utils=hash_utils,
            event_service=event_service,
            **node_kwargs,
        )
        self._allow_event_service_set = False
        provider = self._coerce_history_provider(history_provider)
        self._history_provider = provider
        if provider and hasattr(provider, "bind_stream"):
            provider.bind_stream(self)
        if self.event_service and hasattr(self.event_service, "bind_stream"):
            self.event_service.bind_stream(self)

    @property
    def history_provider(self) -> HistoryProvider | None:
        return self._history_provider

    @history_provider.setter
    def history_provider(self, value: "HistoryProvider" | None) -> None:
        raise AttributeError("history_provider is read-only and must be provided via __init__")

    @property
    def event_recorder(self) -> "EventRecorder" | None:
        if self.event_service is None:
            return None
        return getattr(self.event_service, "recorder", None)

    @event_recorder.setter
    def event_recorder(self, value: "EventRecorder" | None) -> None:
        raise AttributeError("event_recorder is read-only and must be provided via __init__")

    @property
    def event_service(self) -> EventRecorderService | None:
        return getattr(self, "_event_service", None)

    @event_service.setter
    def event_service(self, value: EventRecorderService | None) -> None:
        if getattr(self, "_allow_event_service_set", False) and not hasattr(self, "_event_service_initialized"):
            self._event_service = value
            self._event_service_initialized = True
            return
        raise AttributeError("event_service is read-only and must be provided via __init__")

    async def load_history(self, start: int, end: int) -> None:
        if not self.history_provider or self.interval is None:
            return
        import importlib

        BackfillEngine = getattr(
            importlib.import_module("qmtl.runtime.sdk.backfill_engine"), "BackfillEngine"
        )
        engine = BackfillEngine(self.history_provider)
        engine.submit(self, start, end)
        await engine.wait()

    # ------------------------------------------------------------------
    def _coerce_history_provider(
        self,
        provider: HistoryProvider | HistoryBackend | object | None,
    ) -> HistoryProvider | None:
        if provider is None:
            return None
        if isinstance(provider, HistoryProvider):
            return provider
        if isinstance(provider, HistoryBackend):
            from qmtl.runtime.sdk.history_provider_facade import (
                AugmentedHistoryProvider,
            )

            return AugmentedHistoryProvider(provider)
        return cast(HistoryProvider, provider)


class TagQueryNode(SourceNode):
    """Node that selects upstream queues by tag and interval.

    Parameters
    ----------
    query_tags:
        Tags to subscribe to.
    interval:
        Bar interval in seconds or string shorthand.
    period:
        Number of bars to retain in the cache.
    match_mode:
        Tag matching mode. ``MatchMode.ANY`` subscribes to queues containing
        any of ``query_tags`` while ``MatchMode.ALL`` requires every tag.
        Strings such as ``"any"`` or ``"all"`` are also accepted and
        normalized to the corresponding :class:`MatchMode` value.
    """

    def __init__(
        self,
        query_tags: list[str],
        *,
        interval: int | str,
        period: int,
        match_mode: MatchMode | str = MatchMode.ANY,
        compute_fn=None,
        name: str | None = None,
    ) -> None:
        if not isinstance(query_tags, list):
            raise InvalidParameterError("query_tags must be a list")
        if not query_tags:
            raise InvalidParameterError("query_tags must not be empty")

        validated_query_tags = []
        seen_tags = set()
        for tag in query_tags:
            validated_tag = default_validator.validate_tag(tag)
            if validated_tag in seen_tags:
                raise InvalidParameterError(f"duplicate query tag: {validated_tag!r}")
            seen_tags.add(validated_tag)
            validated_query_tags.append(validated_tag)

        if isinstance(match_mode, MatchMode):
            normalized_mode = match_mode
        else:
            normalized_mode = normalize_match_mode(match_mode)

        normalized_interval = parse_interval(interval)
        canonical_params = canonical_tag_query_params(
            validated_query_tags,
            interval=normalized_interval,
            match_mode=normalized_mode,
            require_tags=True,
            require_interval=True,
        )
        self._tagquery_params = {
            "query_tags": list(canonical_params["query_tags"]),
            "match_mode": canonical_params["match_mode"],
            "interval": canonical_params["interval"],
        }
        self.query_tags = list(self._tagquery_params["query_tags"])
        self.match_mode = normalized_mode

        super().__init__(
            input=None,
            compute_fn=compute_fn,
            name=name or "tag_query",
            interval=normalized_interval,
            period=period,
            tags=list(self.query_tags),
            config=self._tagquery_params,
        )
        self.upstreams: list[str] = []
        self.execute = False

    def _canonical_spec(self):
        spec = super()._canonical_spec()
        spec.with_params(self._tagquery_params)
        spec.update_extras(
            {
                "tags": list(self._tagquery_params["query_tags"]),
                "match_mode": self._tagquery_params["match_mode"],
            }
        )
        return spec

    def update_queues(self, queues: list[str]) -> None:
        prev_exec = self.execute
        prev_set = set(self.upstreams)
        new_set = set(queues)
        added = new_set - prev_set
        removed = prev_set - new_set

        self.upstreams = list(queues)
        self.execute = bool(queues)

        warmup_reset = False
        if added:
            self.pre_warmup = True
            warmup_reset = True

        if removed and self.interval is not None:
            for q in removed:
                self.cache.drop(q, self.interval)

        if not self.upstreams:
            logger.warning(
                "tag_query.update.empty",
                extra={"node_id": self.node_id},
            )

        if (
            self.execute != prev_exec
            or added
            or removed
            or self.upstreams != list(prev_set)
        ):
            logger.info(
                "tag_query.update",
                extra={
                    "node_id": self.node_id,
                    "queues": self.upstreams,
                    "execute": self.execute,
                    "warmup_reset": warmup_reset,
                },
            )
