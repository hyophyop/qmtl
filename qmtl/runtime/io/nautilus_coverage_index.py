"""Coverage index for Nautilus Trader Data Catalog.

This module provides efficient coverage queries for Nautilus catalogs by
scanning Parquet file metadata and caching timestamp ranges.

The index dramatically speeds up coverage queries by avoiding full data reads.

Example::

    from pathlib import Path
    from qmtl.runtime.io.nautilus_coverage_index import NautilusCoverageIndex
    
    # Build index once
    index = NautilusCoverageIndex(
        catalog_path=Path("~/.nautilus/catalog"),
        index_path=Path("~/.qmtl/nautilus_coverage.json"),
    )
    await index.build_index()
    
    # Fast coverage queries
    coverage = index.get_coverage(
        node_id="ohlcv:binance:BTC/USDT:1m",
        interval=60,
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

# Check if pyarrow is available
try:
    import pyarrow.parquet as pq
    PYARROW_AVAILABLE = True
except ImportError:
    PYARROW_AVAILABLE = False
    pq = None


def check_pyarrow_available() -> None:
    """Raise ImportError if pyarrow is not installed."""
    if not PYARROW_AVAILABLE:
        raise ImportError(
            "pyarrow is required for NautilusCoverageIndex. "
            "Install with: uv pip install pyarrow"
        )


class NautilusCoverageIndex:
    """Build and query coverage index for Nautilus Data Catalog.
    
    This class scans Parquet files in a Nautilus catalog and builds an index
    of available timestamp ranges for each (venue, instrument, data_type).
    
    The index is persisted to disk as JSON and can be incrementally updated.
    
    Parameters
    ----------
    catalog_path
        Path to Nautilus catalog root directory.
    index_path
        Path to save/load the coverage index JSON file.
    auto_save
        Automatically save index after building or updating.
    
    Examples
    --------
    >>> index = NautilusCoverageIndex(
    ...     catalog_path=Path("~/.nautilus/catalog"),
    ...     index_path=Path("~/.qmtl/nautilus_coverage.json"),
    ... )
    >>> await index.build_index()
    >>> coverage = index.get_coverage("ohlcv:binance:BTC/USDT:1m", interval=60)
    """
    
    def __init__(
        self,
        catalog_path: Path,
        index_path: Path,
        *,
        auto_save: bool = True,
    ) -> None:
        check_pyarrow_available()
        
        self.catalog_path = catalog_path.expanduser().resolve()
        self.index_path = index_path.expanduser().resolve()
        self.auto_save = auto_save
        
        # Index structure: {node_id: [(start_ts, end_ts), ...]}
        self._index: dict[str, list[tuple[int, int]]] = {}
        self._metadata: dict[str, Any] = {
            "created_at": None,
            "updated_at": None,
            "catalog_path": str(self.catalog_path),
            "file_count": 0,
        }
        
        # Load existing index if available
        if self.index_path.exists():
            self._load_index()
    
    async def build_index(self, *, force: bool = False) -> None:
        """Scan catalog and build coverage index.
        
        Parameters
        ----------
        force
            Force rebuild even if index exists.
        
        Notes
        -----
        This operation can take several minutes for large catalogs.
        Progress is logged at INFO level.
        """
        if not force and self._index:
            logger.info(
                "nautilus.coverage_index.already_built",
                extra={"entries": len(self._index)},
            )
            return
        
        if not self.catalog_path.exists():
            raise FileNotFoundError(
                f"Catalog path not found: {self.catalog_path}"
            )
        
        logger.info(
            "nautilus.coverage_index.build_start",
            extra={"catalog_path": str(self.catalog_path)},
        )
        
        self._index.clear()
        file_count = 0
        
        # Scan Parquet files
        # Nautilus structure: {catalog}/{venue}/{instrument_id}/{data_type}/*.parquet
        for parquet_file in self.catalog_path.rglob("*.parquet"):
            try:
                await self._process_parquet_file(parquet_file)
                file_count += 1
                
                if file_count % 100 == 0:
                    logger.info(
                        "nautilus.coverage_index.progress",
                        extra={"files_processed": file_count},
                    )
            except Exception as exc:
                logger.warning(
                    "nautilus.coverage_index.file_failed",
                    extra={"path": str(parquet_file), "error": str(exc)},
                )
        
        # Update metadata
        self._metadata["created_at"] = datetime.utcnow().isoformat()
        self._metadata["updated_at"] = self._metadata["created_at"]
        self._metadata["file_count"] = file_count
        
        logger.info(
            "nautilus.coverage_index.build_complete",
            extra={
                "entries": len(self._index),
                "files": file_count,
            },
        )
        
        if self.auto_save:
            self._save_index()
    
    async def _process_parquet_file(self, path: Path) -> None:
        """Process a single Parquet file and extract coverage."""
        # Read Parquet metadata without loading full data
        try:
            pf = pq.ParquetFile(path)
        except Exception:
            return

        if pf.num_row_groups == 0:
            return

        # Extract min/max timestamps (in nanoseconds) from statistics
        min_ts_ns = None
        max_ts_ns = None

        try:
            ts_col_idx = pf.schema.names.index('ts_event')
        except ValueError:
            return

        for i in range(pf.num_row_groups):
            stats = pf.metadata.row_group(i).column(ts_col_idx).statistics
            if stats and stats.has_min_max:
                if min_ts_ns is None or stats.min < min_ts_ns:
                    min_ts_ns = stats.min
                if max_ts_ns is None or stats.max > max_ts_ns:
                    max_ts_ns = stats.max

        if min_ts_ns is None or max_ts_ns is None:
            return

        # Convert to seconds
        min_ts = int(min_ts_ns) // 1_000_000_000
        max_ts = int(max_ts_ns) // 1_000_000_000
        
        # Parse file path to get node_id
        node_id = self._parse_node_id_from_path(path)
        if not node_id:
            logger.debug(
                "nautilus.coverage_index.unparseable_path",
                extra={"path": str(path)},
            )
            return
        
        # Add to index
        if node_id not in self._index:
            self._index[node_id] = []
        
        self._index[node_id].append((min_ts, max_ts))
    
    def _parse_node_id_from_path(self, path: Path) -> str | None:
        """Parse QMTL node_id from Nautilus Parquet file path.
        
        Expected structure:
        {catalog}/{venue}/{instrument_id}/{data_type}/*.parquet
        """
        try:
            # Find components relative to catalog root
            components = self._get_path_components(path)
            if not components:
                return None
            
            venue, instrument_id, data_type = components
            
            # Normalize instrument_id (BTC-USDT.BINANCE → BTC/USDT)
            instrument = instrument_id.split('.')[0].replace('-', '/')
            
            # Map data_type to QMTL node_id
            return self._map_to_node_id(path, venue, instrument, data_type)
        
        except Exception as exc:
            logger.debug(
                "nautilus.coverage_index.parse_failed",
                extra={"path": str(path), "error": str(exc)},
            )
            return None

    def _get_path_components(self, path: Path) -> tuple[str, str, str] | None:
        """Extract (venue, instrument_id, data_type) from path."""
        parts = path.parts
        catalog_idx = -1
        for i, part in enumerate(parts):
            if part == self.catalog_path.name:
                catalog_idx = i
                break
        
        if catalog_idx == -1 or catalog_idx + 3 >= len(parts):
            return None
            
        return (
            parts[catalog_idx + 1],
            parts[catalog_idx + 2],
            parts[catalog_idx + 3],
        )

    def _map_to_node_id(
        self, path: Path, venue: str, instrument: str, data_type: str
    ) -> str | None:
        """Map components to QMTL node_id string."""
        if data_type == 'bars':
            timeframe = self._parse_timeframe(path.stem)
            return f"ohlcv:{venue}:{instrument}:{timeframe}" if timeframe else None
        
        if data_type == 'ticks':
            return f"tick:{venue}:{instrument}"
        
        if data_type == 'quotes':
            return f"quote:{venue}:{instrument}"
            
        return None
    
    def _parse_timeframe(self, filename: str) -> str | None:
        """Parse timeframe from Nautilus bar filename.
        
        Examples:
        - BTC-USDT.BINANCE-1-MINUTE-LAST → 1m
        - ETH-USDT.BINANCE-5-MINUTE-LAST → 5m
        - BTC-USDT.BINANCE-1-HOUR-LAST → 1h
        """
        # Nautilus bar_type format: {instrument}-{value}-{unit}-{aggregation}
        parts = filename.split('-')
        if len(parts) < 4:
            return None
        
        try:
            value = parts[-3]
            unit = parts[-2].lower()
            
            # Map Nautilus units to QMTL timeframe tokens
            unit_map = {
                'second': 's',
                'minute': 'm',
                'hour': 'h',
                'day': 'd',
                'week': 'w',
            }
            
            unit_suffix = unit_map.get(unit)
            if not unit_suffix:
                return None
            
            return f"{value}{unit_suffix}"
        
        except Exception:
            return None
    
    def get_coverage(
        self, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        """Get coverage ranges for a node_id.
        
        Parameters
        ----------
        node_id
            QMTL node identifier.
        interval
            Data interval in seconds (currently not used).
        
        Returns
        -------
        list[tuple[int, int]]
            List of (start, end) timestamp ranges in Unix seconds.
        """
        # Build cache key
        cache_key = f"{node_id}:{interval}"
        
        # Try exact match first
        if cache_key in self._index:
            return self._merge_ranges(self._index[cache_key], interval)
        
        # Try without interval suffix
        if node_id in self._index:
            return self._merge_ranges(self._index[node_id], interval)
        
        return []
    
    def _merge_ranges(
        self, ranges: list[tuple[int, int]], interval: int = 1
    ) -> list[tuple[int, int]]:
        """Merge overlapping or adjacent timestamp ranges."""
        if not ranges:
            return []
        
        # Sort by start time
        sorted_ranges = sorted(ranges, key=lambda r: r[0])
        
        merged = [sorted_ranges[0]]
        for current in sorted_ranges[1:]:
            last = merged[-1]
            
            # Check if ranges overlap or are adjacent
            if current[0] <= last[1] + interval:
                # Merge by extending the end time
                merged[-1] = (last[0], max(last[1], current[1]))
            else:
                # Add as separate range
                merged.append(current)
        
        return merged
    
    def _save_index(self) -> None:
        """Save index to disk as JSON."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        
        payload = {
            "metadata": self._metadata,
            "index": {
                node_id: list(ranges)
                for node_id, ranges in self._index.items()
            },
        }
        
        with self.index_path.open('w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        
        logger.info(
            "nautilus.coverage_index.saved",
            extra={"path": str(self.index_path), "entries": len(self._index)},
        )
    
    def _load_index(self) -> None:
        """Load index from disk."""
        try:
            with self.index_path.open('r', encoding='utf-8') as f:
                payload = json.load(f)
            
            self._metadata = payload.get("metadata", {})
            
            # Convert lists back to tuples
            self._index = {
                node_id: [tuple(r) for r in ranges]
                for node_id, ranges in payload.get("index", {}).items()
            }
            
            logger.info(
                "nautilus.coverage_index.loaded",
                extra={
                    "path": str(self.index_path),
                    "entries": len(self._index),
                },
            )
        
        except Exception as exc:
            logger.warning(
                "nautilus.coverage_index.load_failed",
                extra={"path": str(self.index_path), "error": str(exc)},
            )
    
    def invalidate(self) -> None:
        """Clear the in-memory index."""
        self._index.clear()
        logger.info("nautilus.coverage_index.invalidated")
    
    def save(self) -> None:
        """Explicitly save index to disk."""
        self._save_index()


__all__ = [
    "NautilusCoverageIndex",
    "check_pyarrow_available",
    "PYARROW_AVAILABLE",
]
