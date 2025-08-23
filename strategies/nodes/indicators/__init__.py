"""Indicator node processors."""

try:  # pragma: no cover - fallback when qmtl is not installed
    from qmtl.sdk.cache_view import CacheView
except ModuleNotFoundError:  # pragma: no cover - for tests without qmtl
    CacheView = dict  # type: ignore[misc,assignment]

__all__ = ["sample_indicator"]


def sample_indicator(data: CacheView | dict) -> int | float:
    """Double the ``value`` entry of the input.

    Accepts either a plain mapping or a :class:`CacheView`. When a
    ``CacheView`` is provided, the latest payload from the first upstream node
    is used.
    """

    if isinstance(data, CacheView):
        try:
            node_view = next(iter(data._data.values()))  # type: ignore[attr-defined]
            interval_view = next(iter(node_view.values()))
            _, payload = interval_view[-1]
        except Exception:
            return 0
        if isinstance(payload, dict):
            return payload.get("value", 0) * 2
        return 0

    return data.get("value", 0) * 2
