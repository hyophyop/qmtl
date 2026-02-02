"""Example: Using Nautilus Trader DataCatalog with QMTL Seamless provider.

This example demonstrates how to integrate Nautilus Trader's persisted data
with QMTL's Seamless Data Provider for transparent backtesting.

Prerequisites:
1. Install Nautilus Trader integration:
   ```bash
   uv pip install qmtl[nautilus]
   ```

2. Prepare Nautilus catalog with data:
   ```python
   # Using Nautilus to persist data
   from nautilus_trader.persistence.catalog import DataCatalog
   catalog = DataCatalog("~/.nautilus/catalog")
   # ... write data using Nautilus ...
   ```

3. Run this example:
   ```bash
   uv run python examples/nautilus_catalog_example.py
   ```
"""

from __future__ import annotations

import asyncio
import polars as pl
from pathlib import Path

# QMTL imports
from qmtl.runtime.io.nautilus_catalog_source import (
    NautilusCatalogDataSource,
    check_nautilus_available,
)
from qmtl.runtime.sdk.seamless_data_provider import (
    SeamlessDataProvider,
    DataAvailabilityStrategy,
)
from qmtl.runtime.sdk import Strategy, StreamInput

# Nautilus imports (only if installed)
try:
    from nautilus_trader.persistence.catalog import DataCatalog
    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False
    DataCatalog = None


async def example_basic_fetch():
    """Example 1: Basic data fetch from Nautilus catalog."""
    print("=== Example 1: Basic Fetch ===\n")
    
    # Check if Nautilus is available
    try:
        check_nautilus_available()
    except ImportError as e:
        print(f"Error: {e}")
        print("Install with: uv pip install qmtl[nautilus]")
        return
    
    # Setup Nautilus catalog
    catalog_path = Path("~/.nautilus/catalog").expanduser()
    if not catalog_path.exists():
        print(f"Nautilus catalog not found at {catalog_path}")
        print("Create a catalog and add data first using Nautilus Trader")
        return
    
    catalog = DataCatalog(str(catalog_path))
    
    # Create QMTL adapter
    nautilus_source = NautilusCatalogDataSource(
        catalog=catalog,
        coverage_cache_ttl=3600,  # 1 hour cache
    )
    
    # Wrap in Seamless provider
    provider = SeamlessDataProvider(
        strategy=DataAvailabilityStrategy.SEAMLESS,
        storage_source=nautilus_source,
    )
    
    # Fetch OHLCV bars
    print("Fetching OHLCV bars...")
    try:
        bars = await provider.fetch(
            start=1700000000,
            end=1700003600,
            node_id="ohlcv:binance:BTC/USDT:1m",
            interval=60,
        )
        
        print(f"Retrieved {len(bars)} bars")
        if not bars.is_empty():
            print("\nFirst 5 rows:")
            print(bars.head())
            print(f"\nColumns: {list(bars.columns)}")
            print(f"\nTimestamp range: {bars['ts'].min()} - {bars['ts'].max()}")
    except Exception as e:
        print(f"Fetch failed: {e}")
        print("Make sure the instrument exists in your Nautilus catalog")


async def example_ticks_and_quotes():
    """Example 2: Fetching ticks and quotes from Nautilus catalog."""
    print("\n=== Example 2: Ticks and Quotes ===\n")
    
    try:
        check_nautilus_available()
    except ImportError:
        return
    
    catalog_path = Path("~/.nautilus/catalog").expanduser()
    if not catalog_path.exists():
        return
    
    catalog = DataCatalog(str(catalog_path))
    nautilus_source = NautilusCatalogDataSource(catalog=catalog)
    provider = SeamlessDataProvider(storage_source=nautilus_source)
    
    # Fetch trade ticks
    print("Fetching trade ticks...")
    try:
        ticks = await provider.fetch(
            start=1700000000,
            end=1700001000,
            node_id="tick:binance:BTC/USDT",
            interval=1,
        )
        
        print(f"Retrieved {len(ticks)} ticks")
        if not ticks.is_empty():
            print("\nFirst 5 ticks:")
            print(ticks.head())
            print(f"\nColumns: {list(ticks.columns)}")
    except Exception as e:
        print(f"Tick fetch failed: {e}")
    
    # Fetch quote ticks
    print("\n\nFetching quote ticks...")
    try:
        quotes = await provider.fetch(
            start=1700000000,
            end=1700001000,
            node_id="quote:binance:BTC/USDT",
            interval=1,
        )
        
        print(f"Retrieved {len(quotes)} quotes")
        if not quotes.is_empty():
            print("\nFirst 5 quotes:")
            print(quotes.head())
            print(f"\nColumns: {list(quotes.columns)}")
    except Exception as e:
        print(f"Quote fetch failed: {e}")


async def example_strategy_integration():
    """Example 3: Using Nautilus data in a QMTL strategy."""
    print("\n=== Example 3: Strategy Integration ===\n")
    
    try:
        check_nautilus_available()
    except ImportError:
        return
    
    catalog_path = Path("~/.nautilus/catalog").expanduser()
    if not catalog_path.exists():
        print("Catalog not found. Skipping strategy example.")
        return
    
    # Setup provider
    catalog = DataCatalog(str(catalog_path))
    nautilus_source = NautilusCatalogDataSource(catalog=catalog)
    provider = SeamlessDataProvider(storage_source=nautilus_source)
    
    # Define a simple strategy
    class NautilusBacktestStrategy(Strategy):
        """Example strategy using Nautilus-backed data."""
        
        def setup(self):
            # OHLCV bars from Nautilus
            self.price = StreamInput(
                tags=["btc", "spot"],
                interval="60s",
                period=100,
                history_provider=provider,
                node_id_override="ohlcv:binance:BTC/USDT:1m",
            )
            
            # Trade ticks from Nautilus
            self.ticks = StreamInput(
                tags=["btc", "ticks"],
                interval="1s",
                period=1000,
                history_provider=provider,
                node_id_override="tick:binance:BTC/USDT",
            )
            
            # Define compute logic
            def compute(view):
                # Access latest 10 bars
                bars = view[self.price][10]
                if not bars.is_empty():
                    print(f"Latest close: {bars.get_column('close')[-1]}")
                
                # Access latest 100 ticks
                ticks = view[self.ticks][100]
                if not ticks.is_empty():
                    print(f"Latest tick price: {ticks.get_column('price')[-1]}")
            
            self.compute = compute
    
    # Instantiate strategy
    strategy = NautilusBacktestStrategy()
    strategy.setup()
    
    print("Strategy configured with Nautilus data sources")
    print(f"- Price stream: {strategy.price.tags}")
    print(f"- Tick stream: {strategy.ticks.tags}")


async def example_coverage_check():
    """Example 4: Checking data coverage."""
    print("\n=== Example 4: Coverage Check ===\n")
    
    try:
        check_nautilus_available()
    except ImportError:
        return
    
    catalog_path = Path("~/.nautilus/catalog").expanduser()
    if not catalog_path.exists():
        return
    
    catalog = DataCatalog(str(catalog_path))
    nautilus_source = NautilusCatalogDataSource(catalog=catalog)
    
    # Check coverage for different instruments
    instruments = [
        "ohlcv:binance:BTC/USDT:1m",
        "ohlcv:binance:ETH/USDT:1m",
        "tick:binance:BTC/USDT",
    ]
    
    for node_id in instruments:
        print(f"\nChecking coverage for: {node_id}")
        try:
            coverage = await nautilus_source.coverage(
                node_id=node_id,
                interval=60,
            )
            
            if coverage:
                print(f"  Available ranges: {len(coverage)}")
                for start, end in coverage[:3]:  # Show first 3 ranges
                    print(f"    {start} - {end}")
            else:
                print("  No data available")
        except Exception as e:
            print(f"  Coverage check failed: {e}")


async def example_timestamp_conversion():
    """Example 5: Demonstrate timestamp conversion."""
    print("\n=== Example 5: Timestamp Conversion ===\n")
    
    try:
        check_nautilus_available()
    except ImportError:
        return
    
    # Show how Nautilus nanosecond timestamps convert to QMTL seconds
    print("Timestamp conversion demonstration:")
    print("-" * 50)
    
    nautilus_ns = 1700000000 * 1_000_000_000
    qmtl_sec = nautilus_ns // 1_000_000_000
    
    print(f"Nautilus timestamp (ns): {nautilus_ns}")
    print(f"QMTL timestamp (sec):    {qmtl_sec}")
    print(f"Difference factor:       1,000,000,000")
    
    # Show in polars
    df_nautilus = pl.DataFrame([
        {'ts_event': 1700000000 * 1_000_000_000},
        {'ts_event': 1700000060 * 1_000_000_000},
    ])
    
    df_qmtl = df_nautilus.with_columns(
        (pl.col('ts_event') // 1_000_000_000).cast(pl.Int64).alias('ts')
    ).select(['ts'])
    
    print("\n\nExample conversion in DataFrame:")
    print("Nautilus (nanoseconds):")
    print(df_nautilus)
    print("\nQMTL (seconds):")
    print(df_qmtl)


async def example_nautilus_full_preset():
    """Example 6: Using nautilus.full preset (Historical + Live)."""
    print("\n=== Example 6: Nautilus Full Preset (Historical + Live) ===\n")
    
    try:
        check_nautilus_available()
    except ImportError:
        print("nautilus_trader not installed. Skipping.")
        return
    
    from qmtl.runtime.sdk.seamless import SeamlessBuilder
    
    print("nautilus.full preset combines:")
    print("  - Historical data: Nautilus DataCatalog (Parquet)")
    print("  - Live data: CCXT Pro WebSocket\n")
    
    # Example configuration (would be used with real catalog)
    config = {
        "catalog_path": "~/.nautilus/catalog",
        "exchange_id": "binance",
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "timeframe": "1m",
        "mode": "ohlcv",
    }
    
    print("Configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    print("\n\nTo use this preset:")
    print("""
    from qmtl.runtime.sdk.seamless import SeamlessBuilder

    builder = SeamlessBuilder()
    builder = builder.apply_preset("nautilus.full", {
        "catalog_path": "~/.nautilus/catalog",
        "exchange_id": "binance",
        "symbols": ["BTC/USDT"],
        "timeframe": "1m",
    })

    assembly = builder.build()
    provider = assembly.provider

    # Historical fetch
    hist = await provider.fetch(start, end, node_id="...", interval=60)

    # Live streaming
    async for ts, df in provider.stream(node_id="...", interval=60):
        process(df)
    """)


async def main():
    """Run all examples."""
    print("Nautilus Trader × QMTL Integration Examples")
    print("=" * 60)
    
    await example_basic_fetch()
    await example_ticks_and_quotes()
    await example_strategy_integration()
    await example_coverage_check()
    await example_timestamp_conversion()
    await example_nautilus_full_preset()
    
    print("\n" + "=" * 60)
    print("Examples complete!")


if __name__ == "__main__":
    asyncio.run(main())
