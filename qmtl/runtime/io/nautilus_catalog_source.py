"""Nautilus Trader Data Catalog integration for QMTL Seamless Data Provider.

This module provides a :class:`DataSource` adapter that allows QMTL's Seamless
provider to transparently read data from Nautilus Trader's Parquet-based
DataCatalog.

The adapter supports:
- OHLCV bars (with timeframe conversion)
- Trade ticks
- Quote ticks (bid/ask)

Install with::

    uv pip install qmtl[nautilus]

Example::

    from nautilus_trader.persistence.catalog import DataCatalog
    from qmtl.runtime.io.nautilus_catalog_source import NautilusCatalogDataSource
    from qmtl.runtime.sdk.seamless_data_provider import SeamlessDataProvider
    
    catalog = DataCatalog("~/.nautilus/catalog")
    source = NautilusCatalogDataSource(catalog=catalog)
    provider = SeamlessDataProvider(storage_source=source)
    
    # Fetch OHLCV bars
    df = await provider.fetch(
        start=1700000000,
        end=1700003600,
        node_id="ohlcv:binance:BTC/USDT:1m",
        interval=60,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
import pandas as pd
import time
import logging

from qmtl.runtime.sdk.seamless_data_provider import (
    DataSourcePriority,
)

if TYPE_CHECKING:  # pragma: no cover
    # Avoid hard dependency on nautilus_trader
    from nautilus_trader.persistence.catalog import DataCatalog

logger = logging.getLogger(__name__)

# Check if nautilus_trader is available
try:
    from nautilus_trader.persistence.catalog import DataCatalog as _NautilusDataCatalog
    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False
    _NautilusDataCatalog = None


def check_nautilus_available() -> None:
    """Raise ImportError if nautilus_trader is not installed."""
    if not NAUTILUS_AVAILABLE:
        raise ImportError(
            "nautilus_trader is required for NautilusCatalogDataSource. "
            "Install with: uv pip install qmtl[nautilus]"
        )


@dataclass(frozen=True)
class NautilusIdentifier:
    """Parsed identifier for Nautilus catalog queries."""
    
    data_type: str  # 'bar', 'tick', 'quote'
    venue: str
    instrument: str
    bar_type: str | None = None  # Only for bars


def parse_qmtl_node_id(node_id: str) -> NautilusIdentifier:
    """Parse QMTL node_id into Nautilus catalog identifiers.
    
    Supported formats:
    - ``ohlcv:{exchange}:{symbol}:{timeframe}`` → bars
    - ``tick:{venue}:{instrument}`` → trade ticks
    - ``quote:{venue}:{instrument}`` → quote ticks
    
    Parameters
    ----------
    node_id
        QMTL node identifier.
    
    Returns
    -------
    NautilusIdentifier
        Parsed identifier for Nautilus queries.
    
    Raises
    ------
    ValueError
        If node_id format is not supported.
    
    Examples
    --------
    >>> parse_qmtl_node_id("ohlcv:binance:BTC/USDT:1m")
    NautilusIdentifier(data_type='bar', venue='binance', ...)
    
    >>> parse_qmtl_node_id("tick:binance:BTC/USDT")
    NautilusIdentifier(data_type='tick', venue='binance', ...)
    """
    parts = node_id.split(':')
    if len(parts) < 3:
        raise ValueError(
            f"Invalid node_id format: {node_id}. "
            "Expected 'ohlcv:exchange:symbol:timeframe', 'tick:venue:instrument', "
            "or 'quote:venue:instrument'"
        )
    
    prefix = parts[0]
    
    if prefix == 'ohlcv':
        if len(parts) != 4:
            raise ValueError(
                f"OHLCV node_id must have 4 parts: {node_id}"
            )
        venue = parts[1]
        instrument = parts[2]
        timeframe = parts[3]
        # Nautilus bar_type format: {instrument}-{timeframe}-{aggregation}
        bar_type = f"{instrument}-{timeframe}-LAST"
        return NautilusIdentifier(
            data_type='bar',
            venue=venue,
            instrument=instrument,
            bar_type=bar_type,
        )
    
    elif prefix == 'tick':
        venue = parts[1]
        instrument = parts[2]
        return NautilusIdentifier(
            data_type='tick',
            venue=venue,
            instrument=instrument,
        )
    
    elif prefix == 'quote':
        venue = parts[1]
        instrument = parts[2]
        return NautilusIdentifier(
            data_type='quote',
            venue=venue,
            instrument=instrument,
        )
    
    else:
        raise ValueError(
            f"Unsupported node_id prefix: {prefix}. "
            "Expected 'ohlcv', 'tick', or 'quote'"
        )


class NautilusCatalogDataSource:
    """Nautilus Trader DataCatalog adapter for QMTL Seamless provider.
    
    This class wraps a Nautilus DataCatalog and exposes it as a QMTL
    :class:`DataSource`, enabling transparent data access across both
    Nautilus-persisted data and QMTL's native sources.
    
    The adapter handles:
    - Timestamp conversion (Nautilus nanoseconds → QMTL seconds)
    - Schema normalization (Decimal → float64, column renaming)
    - Coverage caching for performance
    
    Parameters
    ----------
    catalog
        Nautilus DataCatalog instance.
    priority
        Data source priority for Seamless orchestration.
    coverage_cache_ttl
        Coverage cache TTL in seconds.
    
    Examples
    --------
    >>> from nautilus_trader.persistence.catalog import DataCatalog
    >>> catalog = DataCatalog("~/.nautilus/catalog")
    >>> source = NautilusCatalogDataSource(catalog=catalog)
    >>> 
    >>> # Use with SeamlessDataProvider
    >>> from qmtl.runtime.sdk.seamless_data_provider import SeamlessDataProvider
    >>> provider = SeamlessDataProvider(storage_source=source)
    """
    
    def __init__(
        self,
        catalog: "DataCatalog",
        *,
        priority: DataSourcePriority = DataSourcePriority.STORAGE,
        coverage_cache_ttl: int = 3600,
    ) -> None:
        check_nautilus_available()
        
        self.catalog = catalog
        self.priority = priority
        self._coverage_cache: dict[str, tuple[float, list[tuple[int, int]]]] = {}
        self._coverage_cache_ttl = coverage_cache_ttl
    
    async def is_available(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> bool:
        """Check if data is available for the given range.
        
        Parameters
        ----------
        start
            Start timestamp (Unix seconds).
        end
            End timestamp (Unix seconds).
        node_id
            QMTL node identifier.
        interval
            Data interval in seconds.
        
        Returns
        -------
        bool
            True if data is available for the full range.
        """
        coverage = await self.coverage(node_id=node_id, interval=interval)
        for range_start, range_end in coverage:
            if range_start <= start and end <= range_end:
                return True
        return False
    
    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Fetch data from Nautilus Catalog.
        
        Parameters
        ----------
        start
            Start timestamp (Unix seconds).
        end
            End timestamp (Unix seconds).
        node_id
            QMTL node identifier.
        interval
            Data interval in seconds.
        
        Returns
        -------
        pd.DataFrame
            Data in QMTL schema (ts column in Unix seconds).
        
        Raises
        ------
        ValueError
            If node_id format is invalid.
        RuntimeError
            If Nautilus catalog read fails.
        """
        identifier = parse_qmtl_node_id(node_id)
        
        # Convert QMTL timestamps (seconds) to Nautilus (nanoseconds)
        start_ns = start * 1_000_000_000
        end_ns = end * 1_000_000_000
        
        logger.debug(
            "nautilus.fetch",
            extra={
                "node_id": node_id,
                "data_type": identifier.data_type,
                "venue": identifier.venue,
                "instrument": identifier.instrument,
                "start": start,
                "end": end,
            },
        )
        
        try:
            if identifier.data_type == 'bar':
                df = self._fetch_bars(identifier, start_ns, end_ns)
            elif identifier.data_type == 'tick':
                df = self._fetch_ticks(identifier, start_ns, end_ns)
            elif identifier.data_type == 'quote':
                df = self._fetch_quotes(identifier, start_ns, end_ns)
            else:
                raise ValueError(f"Unsupported data type: {identifier.data_type}")
        except Exception as exc:
            logger.error(
                "nautilus.fetch.failed",
                extra={
                    "node_id": node_id,
                    "error": str(exc),
                },
            )
            raise RuntimeError(
                f"Failed to fetch {identifier.data_type} data from Nautilus: {exc}"
            ) from exc
        
        # Convert to QMTL schema
        result = self._normalize_to_qmtl(df, identifier.data_type)
        
        logger.debug(
            "nautilus.fetch.success",
            extra={
                "node_id": node_id,
                "rows": len(result),
            },
        )
        
        return result
    
    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        """Return timestamp ranges available for this node.
        
        Parameters
        ----------
        node_id
            QMTL node identifier.
        interval
            Data interval in seconds.
        
        Returns
        -------
        list[tuple[int, int]]
            List of (start, end) timestamp ranges in Unix seconds.
        
        Notes
        -----
        Results are cached for ``coverage_cache_ttl`` seconds to avoid
        repeated filesystem scans.
        """
        # Check cache first
        cache_key = f"{node_id}:{interval}"
        if cache_key in self._coverage_cache:
            cached_at, ranges = self._coverage_cache[cache_key]
            if time.time() - cached_at < self._coverage_cache_ttl:
                logger.debug(
                    "nautilus.coverage.cache_hit",
                    extra={"node_id": node_id, "ranges": len(ranges)},
                )
                return ranges
        
        # Query Nautilus catalog for available data ranges
        identifier = parse_qmtl_node_id(node_id)
        ranges = self._query_coverage(identifier)
        
        # Cache the result
        self._coverage_cache[cache_key] = (time.time(), ranges)
        
        logger.debug(
            "nautilus.coverage.computed",
            extra={"node_id": node_id, "ranges": len(ranges)},
        )
        
        return ranges
    
    def _fetch_bars(
        self, identifier: NautilusIdentifier, start_ns: int, end_ns: int
    ) -> pd.DataFrame:
        """Fetch OHLCV bars from Nautilus catalog."""
        bars = self.catalog.read_bars(
            instrument=identifier.instrument,
            bar_type=identifier.bar_type,
            start=start_ns,
            end=end_ns,
        )
        
        # Convert to DataFrame if needed
        if not isinstance(bars, pd.DataFrame):
            if hasattr(bars, 'to_dict'):
                # Single bar object
                bars = pd.DataFrame([bars.to_dict()])
            else:
                # List of bar objects
                bars = pd.DataFrame([bar.to_dict() for bar in bars])
        
        return bars
    
    def _fetch_ticks(
        self, identifier: NautilusIdentifier, start_ns: int, end_ns: int
    ) -> pd.DataFrame:
        """Fetch trade ticks from Nautilus catalog."""
        ticks = self.catalog.read_ticks(
            instrument=identifier.instrument,
            start=start_ns,
            end=end_ns,
        )
        
        if not isinstance(ticks, pd.DataFrame):
            if hasattr(ticks, '__iter__'):
                ticks = pd.DataFrame([tick.to_dict() for tick in ticks])
            else:
                ticks = pd.DataFrame([ticks.to_dict()])
        
        return ticks
    
    def _fetch_quotes(
        self, identifier: NautilusIdentifier, start_ns: int, end_ns: int
    ) -> pd.DataFrame:
        """Fetch quote ticks from Nautilus catalog."""
        quotes = self.catalog.read_quotes(
            instrument=identifier.instrument,
            start=start_ns,
            end=end_ns,
        )
        
        if not isinstance(quotes, pd.DataFrame):
            if hasattr(quotes, '__iter__'):
                quotes = pd.DataFrame([quote.to_dict() for quote in quotes])
            else:
                quotes = pd.DataFrame([quotes.to_dict()])
        
        return quotes
    
    def _normalize_to_qmtl(
        self, df: pd.DataFrame, data_type: str
    ) -> pd.DataFrame:
        """Convert Nautilus schema to QMTL schema.
        
        Handles:
        - Timestamp conversion (nanoseconds → seconds)
        - Column renaming
        - Type conversion (Decimal → float64)
        """
        if df.empty:
            return df
        
        result = pd.DataFrame()
        
        # Convert timestamp from nanoseconds to seconds
        self._normalize_timestamps(df, result, data_type)
        
        # Convert data_type-specific columns
        if data_type == 'bar':
            self._normalize_bars(df, result)
        elif data_type == 'tick':
            self._normalize_ticks(df, result)
        elif data_type == 'quote':
            self._normalize_quotes(df, result)
        else:
            logger.warning(
                "nautilus.normalize.unknown_type",
                extra={"data_type": data_type},
            )
        
        return result

    def _normalize_timestamps(
        self, df: pd.DataFrame, result: pd.DataFrame, data_type: str
    ) -> None:
        """Convert Nautilus timestamps (ns) to QMTL timestamps (s)."""
        import numpy as np
        if 'ts_event' in df.columns:
            result['ts'] = (np.asarray(df['ts_event'].values) // 1_000_000_000).astype('int64')
        elif 'ts_init' in df.columns:
            result['ts'] = (np.asarray(df['ts_init'].values) // 1_000_000_000).astype('int64')
        else:
            logger.warning(
                "nautilus.normalize.missing_timestamp",
                extra={"columns": list(df.columns), "data_type": data_type},
            )

    def _normalize_bars(self, df: pd.DataFrame, result: pd.DataFrame) -> None:
        """Normalize OHLCV bar columns."""
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                result[col] = df[col].astype('float64')

    def _normalize_ticks(self, df: pd.DataFrame, result: pd.DataFrame) -> None:
        """Normalize trade tick columns."""
        if 'price' in df.columns:
            result['price'] = df['price'].astype('float64')
        if 'size' in df.columns:
            result['size'] = df['size'].astype('float64')
        if 'aggressor_side' in df.columns:
            result['side'] = df['aggressor_side'].str.lower()

    def _normalize_quotes(self, df: pd.DataFrame, result: pd.DataFrame) -> None:
        """Normalize quote tick columns."""
        mappings = {
            'bid_price': 'bid',
            'ask_price': 'ask',
            'bid_size': 'bid_size',
            'ask_size': 'ask_size',
        }
        for src, dest in mappings.items():
            if src in df.columns:
                result[dest] = df[src].astype('float64')
    
    def _query_coverage(self, identifier: NautilusIdentifier) -> list[tuple[int, int]]:
        """Query coverage from Nautilus catalog metadata.
        
        This is a simplified implementation that returns a wide range
        if the instrument exists. For production use, consider implementing
        :class:`NautilusCoverageIndex` to scan Parquet file metadata.
        
        TODO: Implement proper coverage scanning via Parquet metadata.
        """
        try:
            # Check if instrument exists in catalog
            instruments = self.catalog.instruments(venue=identifier.venue)
            instrument_ids = {inst.id.value for inst in instruments}
            
            if identifier.instrument in instrument_ids:
                # Return a conservative wide range
                # Actual data availability will be checked during fetch
                logger.debug(
                    "nautilus.coverage.instrument_found",
                    extra={
                        "venue": identifier.venue,
                        "instrument": identifier.instrument,
                    },
                )
                # Return max int32 range as placeholder
                return [(0, 2**31 - 1)]
            else:
                logger.debug(
                    "nautilus.coverage.instrument_not_found",
                    extra={
                        "venue": identifier.venue,
                        "instrument": identifier.instrument,
                        "available": list(instrument_ids)[:5],  # Sample
                    },
                )
                return []
        except Exception as exc:
            logger.warning(
                "nautilus.coverage.query_failed",
                extra={
                    "venue": identifier.venue,
                    "instrument": identifier.instrument,
                    "error": str(exc),
                },
            )
            return []


__all__ = [
    "NautilusCatalogDataSource",
    "NautilusIdentifier",
    "parse_qmtl_node_id",
    "check_nautilus_available",
    "NAUTILUS_AVAILABLE",
]
