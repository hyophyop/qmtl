"""Indicator node processors."""

# ``CacheView`` is optional for consumers outside the core ``qmtl`` package.
try:  # pragma: no cover - soft dependency for tests
    from qmtl.sdk.cache_view import CacheView
except Exception:  # pragma: no cover - fallback when qmtl isn't installed
    class CacheView(dict):
        """Lightweight stub used when :mod:`qmtl` is unavailable."""

        def __getitem__(self, key):  # type: ignore[override]
            return super().__getitem__(key)

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
