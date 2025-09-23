from __future__ import annotations

"""Adapters for optional runtime integrations used by Runner."""

from typing import Any, Callable

from . import runtime


class RayExecutor:
    """Execute compute functions via Ray when available."""

    def __init__(self, *, disabled: bool | None = None) -> None:
        self._disabled = bool(disabled) if disabled is not None else False
        try:  # Optional Ray dependency
            import ray  # type: ignore
        except Exception:  # pragma: no cover - Ray not installed
            self._ray: Any | None = None
        else:  # pragma: no cover - exercised when Ray is installed
            self._ray = ray

    @property
    def available(self) -> bool:
        return not (self._disabled or runtime.NO_RAY) and self._ray is not None

    def execute(self, fn: Callable[[Any], Any], cache_view: Any) -> Any | None:
        """Execute ``fn`` with ``cache_view``.

        Returns the function result when executed locally.  When Ray is
        available the computation is dispatched to the cluster and ``None``
        is returned to mirror the historical Runner behaviour.
        """

        if not self.available:
            return fn(cache_view)

        ray = self._ray
        assert ray is not None  # mypy appeasement
        if not ray.is_initialized():  # type: ignore[attr-defined]
            ray.init(ignore_reinit_error=True)  # type: ignore[attr-defined]
        ray.remote(fn).remote(cache_view)  # type: ignore[attr-defined]
        return None

    def set_disabled(self, disabled: bool) -> None:
        self._disabled = bool(disabled)


class KafkaConsumerFactory:
    """Factory for creating Kafka consumers when aiokafka is installed."""

    def __init__(self) -> None:
        try:  # Optional aiokafka dependency
            from aiokafka import AIOKafkaConsumer  # type: ignore
        except Exception:  # pragma: no cover - aiokafka not installed
            self._consumer_cls: Any | None = None
        else:  # pragma: no cover - exercised when aiokafka is installed
            self._consumer_cls = AIOKafkaConsumer

    @property
    def available(self) -> bool:
        return self._consumer_cls is not None

    def create_consumer(self, topic: str, *, bootstrap_servers: str) -> Any:
        if self._consumer_cls is None:
            raise RuntimeError("aiokafka not available")
        return self._consumer_cls(  # type: ignore[call-arg]
            topic,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=True,
        )


__all__ = ["KafkaConsumerFactory", "RayExecutor"]
