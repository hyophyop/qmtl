"""
QMTL Seamless Data Provider - Usage Examples and Migration Guide

This file demonstrates how to use the new Seamless Data Provider system
for transparent auto-backfill and live data integration.
"""

import asyncio
import pandas as pd

from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy


# Example DataFetcher implementation for demonstration
class ExampleMarketDataFetcher:
    """Example implementation of DataFetcher for market data."""
    
    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Simulate fetching market data from external API."""
        # In real implementation, this would call external market data APIs
        print(f"Fetching {node_id} data from {start} to {end} with interval {interval}")
        
        # Generate sample data
        timestamps = list(range(start, end, interval))
        data = []
        
        for ts in timestamps:
            data.append({
                'ts': ts,
                'node_id': node_id,
                'interval': interval,
                'price': 100.0 + (ts % 1000) * 0.01,  # Sample price data
                'volume': 1000 + (ts % 500),           # Sample volume data
            })
        
        return pd.DataFrame(data)


class ExampleLiveDataFetcher:
    """Example implementation for live data fetching."""
    
    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Simulate fetching current/live market data."""
        print(f"Fetching live {node_id} data from {start} to {end}")
        
        # In real implementation, this would connect to live data feeds
        current_time = pd.Timestamp.now().timestamp()
        current_time = int(current_time)
        
        if start <= current_time < end:
            return pd.DataFrame([{
                'ts': current_time,
                'node_id': node_id,
                'interval': interval,
                'price': 100.5,  # Live price
                'volume': 1500,  # Live volume
            }])
        
        return pd.DataFrame()


async def example_basic_usage():
    """Example 1: Basic seamless data provider usage."""
    print("=== Example 1: Basic Usage ===")
    
    # Create data fetchers
    historical_fetcher = ExampleMarketDataFetcher()
    live_fetcher = ExampleLiveDataFetcher()
    
    # Create seamless provider
    provider = EnhancedQuestDBProvider(
        dsn="postgresql://localhost:8812/qmtl",
        table="market_data",
        fetcher=historical_fetcher,
        live_fetcher=live_fetcher,
        strategy=DataAvailabilityStrategy.SEAMLESS
    )
    
    # Fetch data transparently
    # The provider will automatically:
    # 1. Check local storage first
    # 2. Auto-backfill missing data if needed
    # 3. Use live data for recent timestamps
    
    start_time = 1700000000
    end_time = 1700003600
    node_id = "AAPL_price_processor"
    interval = 300  # 5 minutes
    
    data = await provider.fetch(
        start_time, end_time,
        node_id=node_id, interval=interval
    )
    
    print(f"Retrieved {len(data)} rows of data")
    print(data.head() if not data.empty else "No data retrieved")


async def example_strategy_comparison():
    """Example 2: Comparing different data availability strategies."""
    print("\n=== Example 2: Strategy Comparison ===")
    
    historical_fetcher = ExampleMarketDataFetcher()
    
    # Strategy 1: FAIL_FAST - Only use existing data
    provider_fail_fast = EnhancedQuestDBProvider(
        dsn="postgresql://localhost:8812/qmtl",
        fetcher=historical_fetcher,
        strategy=DataAvailabilityStrategy.FAIL_FAST
    )
    
    # Strategy 2: AUTO_BACKFILL - Ensure all data is backfilled
    provider_auto_backfill = EnhancedQuestDBProvider(
        dsn="postgresql://localhost:8812/qmtl",
        fetcher=historical_fetcher,
        strategy=DataAvailabilityStrategy.AUTO_BACKFILL
    )
    
    # Strategy 3: PARTIAL_FILL - Return available, backfill in background
    provider_partial = EnhancedQuestDBProvider(
        dsn="postgresql://localhost:8812/qmtl",
        fetcher=historical_fetcher,
        strategy=DataAvailabilityStrategy.PARTIAL_FILL
    )
    
    start_time = 1700000000
    end_time = 1700001800
    node_id = "AAPL_processor"
    interval = 300
    
    # Try each strategy
    strategies = [
        ("FAIL_FAST", provider_fail_fast),
        ("AUTO_BACKFILL", provider_auto_backfill),
        ("PARTIAL_FILL", provider_partial),
    ]
    
    for strategy_name, provider in strategies:
        try:
            print(f"\nTrying {strategy_name} strategy...")
            data = await provider.fetch(
                start_time, end_time,
                node_id=node_id, interval=interval
            )
            print(f"  Result: {len(data)} rows retrieved")
        except Exception as e:
            print(f"  Result: Failed with {e}")


async def example_migration_from_existing():
    """Example 3: Migration from existing QuestDBLoader."""
    print("\n=== Example 3: Migration Guide ===")
    
    # BEFORE: Using traditional QuestDBLoader
    print("BEFORE (traditional approach):")
    print("""
    from qmtl.runtime.io.historyprovider import QuestDBLoader
    
    provider = QuestDBLoader(
        dsn="postgresql://localhost:8812/qmtl",
        table="market_data",
        fetcher=my_fetcher
    )
    
    # Manual backfill required
    await provider.fill_missing(start, end, node_id=node_id, interval=interval)
    
    # Then fetch data
    data = await provider.fetch(start, end, node_id=node_id, interval=interval)
    """)
    
    # AFTER: Using EnhancedQuestDBProvider
    print("\nAFTER (seamless approach):")
    print("""
    from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
    from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy
    
    provider = EnhancedQuestDBProvider(
        dsn="postgresql://localhost:8812/qmtl",
        table="market_data",
        fetcher=my_fetcher,
        live_fetcher=my_live_fetcher,  # Optional
        strategy=DataAvailabilityStrategy.SEAMLESS  # Automatic handling
    )
    
    # Just fetch - backfill happens automatically
    data = await provider.fetch(start, end, node_id=node_id, interval=interval)
    """)


async def example_stream_input_integration():
    """Example 4: Integration with StreamInput nodes."""
    print("\n=== Example 4: StreamInput Integration ===")
    
    from qmtl.runtime.sdk.nodes.sources import StreamInput
    
    # Create enhanced provider
    provider = EnhancedQuestDBProvider(
        dsn="postgresql://localhost:8812/qmtl",
        table="price_feed",
        fetcher=ExampleMarketDataFetcher(),
        live_fetcher=ExampleLiveDataFetcher(),
        strategy=DataAvailabilityStrategy.SEAMLESS
    )
    
    # Create StreamInput with seamless provider
    stream_input = StreamInput(
        tags=["price", "market_data"],
        interval=300,
        period=3600,
        history_provider=provider  # Uses seamless provider
    )
    
    print("StreamInput created with seamless data provider")
    print(f"Stream node ID: {stream_input.node_id}")
    print("The stream will automatically handle:")
    print("- Historical data loading")
    print("- Auto-backfill of missing data")
    print("- Seamless transition to live data")
    
    # The node can now be used in a strategy DAG
    # and will transparently handle all data requirements


async def example_custom_backfiller():
    """Example 5: Custom backfiller implementation."""
    print("\n=== Example 5: Custom Backfiller ===")
    
    class CustomMarketDataBackfiller:
        """Custom backfiller with specific business logic."""
        
        async def can_backfill(
            self, start: int, end: int, *, node_id: str, interval: int
        ) -> bool:
            # Custom logic to determine if backfill is possible
            # e.g., check market hours, data availability windows, etc.
            print(f"Checking if can backfill {node_id} from {start} to {end}")
            
            # Example: Only backfill during market hours
            # (This is simplified logic)
            return True
        
        async def backfill(
            self, start: int, end: int, *, node_id: str, interval: int,
            target_storage=None
        ) -> pd.DataFrame:
            print(f"Custom backfilling {node_id} from {start} to {end}")
            
            # Custom backfill logic here
            # e.g., call specific APIs, apply data transformations, etc.
            
            # Generate sample data for demonstration
            timestamps = list(range(start, end, interval))
            data = []
            
            for ts in timestamps:
                data.append({
                    'ts': ts,
                    'node_id': node_id,
                    'interval': interval,
                    'custom_field': f"backfilled_{ts}",
                    'price': 100.0 + (ts % 1000) * 0.01,
                })
            
            df = pd.DataFrame(data)
            
            # Store in target storage if provided
            if target_storage and hasattr(target_storage, 'storage_provider'):
                # Custom storage logic here
                pass
            
            return df
        
        async def backfill_async(
            self, start: int, end: int, *, node_id: str, interval: int,
            target_storage=None, progress_callback=None
        ):
            # Custom chunked backfill with progress reporting
            chunk_size = 1800  # 30 minutes
            current = start
            total_duration = end - start
            
            while current < end:
                chunk_end = min(current + chunk_size, end)
                
                chunk_data = await self.backfill(
                    current, chunk_end,
                    node_id=node_id, interval=interval,
                    target_storage=target_storage
                )
                
                if progress_callback:
                    progress = (current - start) / total_duration
                    progress_callback(progress)
                    print(f"Backfill progress: {progress:.2%}")
                
                yield chunk_data
                current = chunk_end
    
    # Use custom backfiller
    print("Custom backfiller created with specialized business logic")
    print("This would be integrated into a custom SeamlessDataProvider implementation")


async def main():
    """Run all examples."""
    print("QMTL Seamless Data Provider Examples")
    print("====================================")
    
    # Run all examples
    await example_basic_usage()
    await example_strategy_comparison()
    await example_migration_from_existing()
    await example_stream_input_integration()
    await example_custom_backfiller()
    
    print("\n=== Summary ===")
    print("The Seamless Data Provider system provides:")
    print("1. Transparent auto-backfill of missing historical data")
    print("2. Seamless integration of live and historical data")
    print("3. Multiple strategies for handling data availability")
    print("4. Background processing capabilities")
    print("5. Full compatibility with existing QMTL components")
    print("\nUsers can migrate gradually and customize behavior as needed.")


if __name__ == "__main__":
    asyncio.run(main())