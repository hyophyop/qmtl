from __future__ import annotations

from typing import Any, Iterable, Iterator, Tuple


class CommitLogDeduplicator:
    """Filter out duplicate commit-log records.

    Records are identified by the triple ``(node_id, bucket_ts, input_window_hash)``.
    Only the first occurrence of each triple is yielded. Subsequent duplicates are
    discarded silently.
    """

    def __init__(self) -> None:
        self._seen: set[Tuple[str, int, str]] = set()

    def filter(
        self, records: Iterable[Tuple[str, int, str, Any]]
    ) -> Iterator[Tuple[str, int, str, Any]]:
        for node_id, bucket_ts, input_hash, payload in records:
            key = (node_id, bucket_ts, input_hash)
            if key in self._seen:
                continue
            self._seen.add(key)
            yield (node_id, bucket_ts, input_hash, payload)


__all__ = ["CommitLogDeduplicator"]
