"""Performance benchmark for Nautilus Trader Catalog integration.

This script measures:
1. Coverage index build time
2. Coverage query performance (with/without index)
3. Data fetch performance
4. Schema conversion overhead

Run with::

    uv run python scripts/benchmark_nautilus_integration.py

Requirements:
- Nautilus catalog with sample data
- pyarrow for Parquet reading
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any
import statistics

try:
    from nautilus_trader.persistence.catalog import DataCatalog
    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False
    DataCatalog = None

from qmtl.runtime.io.nautilus_catalog_source import (
    NautilusCatalogDataSource,
    check_nautilus_available,
)
from qmtl.runtime.io.nautilus_coverage_index import NautilusCoverageIndex
from qmtl.runtime.sdk.seamless_data_provider import SeamlessDataProvider
from qmtl.runtime.sdk.conformance import (
    TickConformanceRule,
    QuoteConformanceRule,
)


class BenchmarkResults:
    """Store and display benchmark results."""
    
    def __init__(self):
        self.results: dict[str, Any] = {}
    
    def add(self, name: str, value: Any) -> None:
        """Add a benchmark result."""
        self.results[name] = value
    
    def print_summary(self) -> None:
        """Print formatted benchmark summary."""
        print("\n" + "=" * 70)
        print("Nautilus Trader Integration Benchmark Results")
        print("=" * 70)
        
        for name, value in self.results.items():
            self._print_result(name, value)
        
        print("=" * 70)
    
    def _print_result(self, name: str, value: Any) -> None:
        """Print a single result."""
        if isinstance(value, dict):
            print(f"\n{name}:")
            for k, v in value.items():
                print(f"  {k}: {v}")
        elif isinstance(value, (int, float)):
            if name.endswith("_ms") or "time" in name.lower():
                print(f"{name}: {value:.2f} ms")
            elif name.endswith("_us"):
                print(f"{name}: {value:.2f} μs")
            else:
                print(f"{name}: {value}")
        else:
            print(f"{name}: {value}")


async def benchmark_coverage_index_build(
    catalog_path: Path,
    results: BenchmarkResults,
) -> NautilusCoverageIndex | None:
    """Benchmark: Build coverage index from scratch."""
    print("\n[1/6] Building coverage index...")
    
    index_path = Path("/tmp/nautilus_coverage_bench.json")
    if index_path.exists():
        index_path.unlink()
    
    index = NautilusCoverageIndex(
        catalog_path=catalog_path,
        index_path=index_path,
        auto_save=False,
    )
    
    start = time.perf_counter()
    await index.build_index(force=True)
    elapsed = (time.perf_counter() - start) * 1000  # ms
    
    results.add("coverage_index_build_time_ms", elapsed)
    results.add("coverage_index_entries", len(index._index))
    results.add("coverage_index_files_scanned", index._metadata.get("file_count", 0))
    
    print(f"  ✓ Built index in {elapsed:.2f} ms")
    print(f"    - Entries: {len(index._index)}")
    print(f"    - Files scanned: {index._metadata.get('file_count', 0)}")
    
    return index


async def benchmark_coverage_query(
    catalog: DataCatalog,
    index: NautilusCoverageIndex | None,
    results: BenchmarkResults,
) -> None:
    """Benchmark: Coverage query performance."""
    print("\n[2/6] Benchmarking coverage queries...")
    
    node_ids = [
        "ohlcv:binance:BTC/USDT:1m",
        "ohlcv:binance:ETH/USDT:1m",
        "tick:binance:BTC/USDT",
    ]
    
    # Without index
    source_no_index = NautilusCatalogDataSource(
        catalog=catalog,
        coverage_cache_ttl=0,  # Disable cache
    )
    
    times_no_index = []
    for node_id in node_ids:
        start = time.perf_counter()
        await source_no_index.coverage(node_id=node_id, interval=60)
        elapsed = (time.perf_counter() - start) * 1000000  # μs
        times_no_index.append(elapsed)
    
    avg_no_index = statistics.mean(times_no_index) if times_no_index else 0
    
    # With index (if available)
    avg_with_index = 0
    if index:
        times_with_index = []
        for node_id in node_ids:
            start = time.perf_counter()
            index.get_coverage(node_id, interval=60)
            elapsed = (time.perf_counter() - start) * 1000000  # μs
            times_with_index.append(elapsed)
        
        avg_with_index = statistics.mean(times_with_index) if times_with_index else 0
    
    results.add("coverage_query_without_index_us", avg_no_index)
    results.add("coverage_query_with_index_us", avg_with_index)
    
    if avg_with_index > 0:
        speedup = avg_no_index / avg_with_index
        results.add("coverage_query_speedup", f"{speedup:.1f}x")
    
    print(f"  ✓ Without index: {avg_no_index:.2f} μs (avg)")
    if avg_with_index > 0:
        print(f"  ✓ With index: {avg_with_index:.2f} μs (avg)")
        print(f"    - Speedup: {avg_no_index / avg_with_index:.1f}x")


async def benchmark_fetch_bars(
    provider: SeamlessDataProvider,
    results: BenchmarkResults,
) -> None:
    """Benchmark: Fetch OHLCV bars."""
    print("\n[3/6] Benchmarking OHLCV bar fetch...")
    
    node_id = "ohlcv:binance:BTC/USDT:1m"
    start_ts = 1700000000
    end_ts = 1700003600  # 1 hour
    
    start = time.perf_counter()
    df = await provider.fetch(
        start=start_ts,
        end=end_ts,
        node_id=node_id,
        interval=60,
    )
    elapsed = (time.perf_counter() - start) * 1000  # ms
    
    results.add("fetch_bars_time_ms", elapsed)
    results.add("fetch_bars_rows", len(df))
    
    if len(df) > 0:
        throughput = len(df) / (elapsed / 1000)  # rows/sec
        results.add("fetch_bars_throughput_rows_per_sec", int(throughput))
    
    print(f"  ✓ Fetched {len(df)} bars in {elapsed:.2f} ms")
    if len(df) > 0:
        print(f"    - Throughput: {len(df) / (elapsed / 1000):.0f} rows/sec")


async def benchmark_fetch_ticks(
    provider: SeamlessDataProvider,
    results: BenchmarkResults,
) -> None:
    """Benchmark: Fetch trade ticks."""
    print("\n[4/6] Benchmarking tick fetch...")
    
    node_id = "tick:binance:BTC/USDT"
    start_ts = 1700000000
    end_ts = 1700001000  # 16 minutes
    
    try:
        start = time.perf_counter()
        df = await provider.fetch(
            start=start_ts,
            end=end_ts,
            node_id=node_id,
            interval=1,
        )
        elapsed = (time.perf_counter() - start) * 1000  # ms
        
        results.add("fetch_ticks_time_ms", elapsed)
        results.add("fetch_ticks_rows", len(df))
        
        if len(df) > 0:
            throughput = len(df) / (elapsed / 1000)
            results.add("fetch_ticks_throughput_rows_per_sec", int(throughput))
        
        print(f"  ✓ Fetched {len(df)} ticks in {elapsed:.2f} ms")
        if len(df) > 0:
            print(f"    - Throughput: {throughput:.0f} rows/sec")
    
    except Exception as e:
        print(f"  ⚠ Tick fetch failed: {e}")
        results.add("fetch_ticks_error", str(e))


async def benchmark_schema_conversion(
    catalog: DataCatalog,
    results: BenchmarkResults,
) -> None:
    """Benchmark: Schema conversion overhead."""
    print("\n[5/6] Benchmarking schema conversion...")
    
    source = NautilusCatalogDataSource(catalog=catalog)
    
    # Fetch raw data (with conversion)
    node_id = "ohlcv:binance:BTC/USDT:1m"
    start_ts = 1700000000 * 1_000_000_000  # nanoseconds
    end_ts = 1700003600 * 1_000_000_000
    
    try:
        # Time just the conversion
        nautilus_df = catalog.read_bars(
            instrument="BTC/USDT",
            bar_type="BTC/USDT-1m-LAST",
            start=start_ts,
            end=end_ts,
        )
        
        start = time.perf_counter()
        qmtl_df = source._normalize_to_qmtl(nautilus_df, 'bar')
        elapsed = (time.perf_counter() - start) * 1000000  # μs
        
        results.add("schema_conversion_time_us", elapsed)
        results.add("schema_conversion_rows", len(qmtl_df))
        
        if len(qmtl_df) > 0:
            per_row = elapsed / len(qmtl_df)
            results.add("schema_conversion_per_row_us", per_row)
        
        print(f"  ✓ Converted {len(qmtl_df)} rows in {elapsed:.2f} μs")
        if len(qmtl_df) > 0:
            print(f"    - Per row: {per_row:.3f} μs")
    
    except Exception as e:
        print(f"  ⚠ Schema conversion benchmark failed: {e}")
        results.add("schema_conversion_error", str(e))


async def benchmark_conformance_rules(results: BenchmarkResults) -> None:
    """Benchmark: Conformance rule validation."""
    print("\n[6/6] Benchmarking conformance rules...")
    
    tick_time = _benchmark_tick_conformance()
    results.add("tick_conformance_time_us", tick_time)
    
    quote_time = _benchmark_quote_conformance()
    results.add("quote_conformance_time_us", quote_time)
    
    print(f"  ✓ Tick validation: {tick_time:.2f} μs")
    print(f"  ✓ Quote validation: {quote_time:.2f} μs")


def _benchmark_tick_conformance() -> float:
    """Benchmark tick data validation."""
    import pandas as pd
    tick_df = pd.DataFrame({
        'ts': list(range(1700000000, 1700001000)),
        'price': [100.0 + i * 0.01 for i in range(1000)],
        'size': [1.0 + i * 0.001 for i in range(1000)],
        'side': ['buy' if i % 2 == 0 else 'sell' for i in range(1000)],
    })
    rule = TickConformanceRule()
    start = time.perf_counter()
    for _ in range(100):
        rule.validate(tick_df)
    return (time.perf_counter() - start) * 1000000 / 100


def _benchmark_quote_conformance() -> float:
    """Benchmark quote data validation."""
    import pandas as pd
    quote_df = pd.DataFrame({
        'ts': list(range(1700000000, 1700001000)),
        'bid': [100.0 + i * 0.01 for i in range(1000)],
        'ask': [100.5 + i * 0.01 for i in range(1000)],
        'bid_size': [10.0 + i * 0.01 for i in range(1000)],
        'ask_size': [8.0 + i * 0.01 for i in range(1000)],
    })
    rule = QuoteConformanceRule()
    start = time.perf_counter()
    for _ in range(100):
        rule.validate(quote_df)
    return (time.perf_counter() - start) * 1000000 / 100


async def run_benchmark(catalog_path: Path) -> BenchmarkResults:
    """Run all benchmarks."""
    results = BenchmarkResults()
    
    print("Nautilus Trader Integration Performance Benchmark")
    print(f"Catalog path: {catalog_path}")
    
    # Check availability
    try:
        check_nautilus_available()
    except ImportError as e:
        print(f"\nError: {e}")
        print("Install with: uv pip install qmtl[nautilus]")
        return results
    
    if not catalog_path.exists():
        print(f"\nError: Catalog not found at {catalog_path}")
        print("Create a catalog with Nautilus Trader first.")
        return results
    
    # Load catalog
    catalog = DataCatalog(str(catalog_path))
    
    # Create provider
    nautilus_source = NautilusCatalogDataSource(catalog=catalog)
    provider = SeamlessDataProvider(storage_source=nautilus_source)
    
    # Run benchmarks
    index = await benchmark_coverage_index_build(catalog_path, results)
    await benchmark_coverage_query(catalog, index, results)
    await benchmark_fetch_bars(provider, results)
    await benchmark_fetch_ticks(provider, results)
    await benchmark_schema_conversion(catalog, results)
    await benchmark_conformance_rules(results)
    
    return results


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Benchmark Nautilus Trader Catalog integration"
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("~/.nautilus/catalog"),
        help="Path to Nautilus catalog (default: ~/.nautilus/catalog)",
    )
    
    args = parser.parse_args()
    
    results = await run_benchmark(args.catalog)
    results.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
