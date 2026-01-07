"""Unit tests for Nautilus Trader DataCatalog integration."""

from __future__ import annotations

import pytest
import pandas as pd
from unittest.mock import Mock
from decimal import Decimal

from qmtl.runtime.io.nautilus_catalog_source import (
    NautilusCatalogDataSource,
    parse_qmtl_node_id,
    check_nautilus_available,
    NAUTILUS_AVAILABLE,
)
from qmtl.runtime.sdk.seamless_data_provider import DataSourcePriority


class TestNodeIdParsing:
    """Test QMTL node_id → Nautilus identifier parsing."""
    
    def test_parse_ohlcv_node_id(self):
        """Parse OHLCV node_id format."""
        identifier = parse_qmtl_node_id("ohlcv:binance:BTC/USDT:1m")
        
        assert identifier.data_type == 'bar'
        assert identifier.venue == 'binance'
        assert identifier.instrument == 'BTC/USDT'
        assert identifier.bar_type == 'BTC/USDT-1m-LAST'
    
    def test_parse_tick_node_id(self):
        """Parse tick node_id format."""
        identifier = parse_qmtl_node_id("tick:binance:BTC/USDT")
        
        assert identifier.data_type == 'tick'
        assert identifier.venue == 'binance'
        assert identifier.instrument == 'BTC/USDT'
        assert identifier.bar_type is None
    
    def test_parse_quote_node_id(self):
        """Parse quote node_id format."""
        identifier = parse_qmtl_node_id("quote:binance:BTC/USDT")
        
        assert identifier.data_type == 'quote'
        assert identifier.venue == 'binance'
        assert identifier.instrument == 'BTC/USDT'
        assert identifier.bar_type is None
    
    def test_parse_invalid_format(self):
        """Reject invalid node_id formats."""
        with pytest.raises(ValueError, match="Invalid node_id format"):
            parse_qmtl_node_id("invalid")
        
        with pytest.raises(ValueError, match="Invalid node_id format"):
            parse_qmtl_node_id("ohlcv:binance")  # Too few parts
    
    def test_parse_unsupported_prefix(self):
        """Reject unsupported node_id prefixes."""
        with pytest.raises(ValueError, match="Unsupported node_id prefix"):
            parse_qmtl_node_id("depth:binance:BTC/USDT")
    
    def test_parse_ohlcv_wrong_parts(self):
        """Reject OHLCV node_id with wrong number of parts."""
        with pytest.raises(ValueError, match="OHLCV node_id must have 4 parts"):
            parse_qmtl_node_id("ohlcv:binance:BTC/USDT")  # Missing timeframe


@pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")
class TestNautilusCatalogDataSource:
    """Test NautilusCatalogDataSource adapter."""
    
    @pytest.fixture
    def mock_catalog(self):
        """Create mock Nautilus DataCatalog."""
        catalog = Mock()
        
        # Mock instruments list
        mock_instrument = Mock()
        mock_instrument.id.value = "BTC/USDT"
        catalog.instruments.return_value = [mock_instrument]
        
        return catalog
    
    @pytest.fixture
    def source(self, mock_catalog):
        """Create NautilusCatalogDataSource instance."""
        return NautilusCatalogDataSource(
            catalog=mock_catalog,
            coverage_cache_ttl=60,
        )
    
    def test_init_sets_priority(self, mock_catalog):
        """Verify priority is set correctly."""
        source = NautilusCatalogDataSource(
            catalog=mock_catalog,
            priority=DataSourcePriority.STORAGE,
        )
        
        assert source.priority == DataSourcePriority.STORAGE
    
    @pytest.mark.asyncio
    async def test_coverage_returns_ranges(self, source, mock_catalog):
        """Coverage returns timestamp ranges for existing instruments."""
        ranges = await source.coverage(
            node_id="ohlcv:binance:BTC/USDT:1m",
            interval=60,
        )
        
        assert len(ranges) > 0
        assert all(isinstance(r, tuple) and len(r) == 2 for r in ranges)
    
    @pytest.mark.asyncio
    async def test_coverage_caching(self, source, mock_catalog):
        """Coverage results are cached."""
        node_id = "ohlcv:binance:BTC/USDT:1m"
        interval = 60
        
        # First call
        ranges1 = await source.coverage(node_id=node_id, interval=interval)
        
        # Second call should use cache
        ranges2 = await source.coverage(node_id=node_id, interval=interval)
        
        assert ranges1 == ranges2
        # Catalog should only be queried once
        assert mock_catalog.instruments.call_count == 1
    
    @pytest.mark.asyncio
    async def test_is_available_checks_coverage(self, source, mock_catalog):
        """is_available checks coverage ranges."""
        # Mock coverage to return specific range
        source._coverage_cache["ohlcv:binance:BTC/USDT:1m:60"] = (
            9999999999,  # Cached timestamp (far future)
            [(1700000000, 1700010000)],  # Available range
        )
        
        # Within range
        available = await source.is_available(
            start=1700001000,
            end=1700002000,
            node_id="ohlcv:binance:BTC/USDT:1m",
            interval=60,
        )
        assert available is True
        
        # Outside range
        available = await source.is_available(
            start=1700020000,
            end=1700030000,
            node_id="ohlcv:binance:BTC/USDT:1m",
            interval=60,
        )
        assert available is False
    
    @pytest.mark.asyncio
    async def test_fetch_bars_converts_schema(self, source, mock_catalog):
        """fetch() converts Nautilus bar schema to QMTL schema."""
        # Mock Nautilus bars data
        nautilus_bars = pd.DataFrame([
            {
                'ts_event': 1700000000 * 1_000_000_000,  # Nanoseconds
                'ts_init': 1700000000 * 1_000_000_000,
                'open': Decimal('100.0'),
                'high': Decimal('101.0'),
                'low': Decimal('99.0'),
                'close': Decimal('100.5'),
                'volume': Decimal('1000.0'),
            },
            {
                'ts_event': 1700000060 * 1_000_000_000,
                'ts_init': 1700000060 * 1_000_000_000,
                'open': Decimal('100.5'),
                'high': Decimal('102.0'),
                'low': Decimal('100.0'),
                'close': Decimal('101.0'),
                'volume': Decimal('1500.0'),
            },
        ])
        
        mock_catalog.read_bars.return_value = nautilus_bars
        
        # Fetch data
        result = await source.fetch(
            start=1700000000,
            end=1700000120,
            node_id="ohlcv:binance:BTC/USDT:1m",
            interval=60,
        )
        
        # Verify schema conversion
        assert 'ts' in result.columns
        assert result['ts'].dtype == 'int64'
        assert result['ts'].iloc[0] == 1700000000  # Converted to seconds
        
        # Verify OHLCV columns
        for col in ['open', 'high', 'low', 'close', 'volume']:
            assert col in result.columns
            assert result[col].dtype == 'float64'
        
        # Verify values
        assert result['open'].iloc[0] == 100.0
        assert result['close'].iloc[1] == 101.0
    
    @pytest.mark.asyncio
    async def test_fetch_ticks_converts_schema(self, source, mock_catalog):
        """fetch() converts Nautilus tick schema to QMTL schema."""
        nautilus_ticks = pd.DataFrame([
            {
                'ts_event': 1700000000 * 1_000_000_000,
                'ts_init': 1700000000 * 1_000_000_000,
                'price': Decimal('100.5'),
                'size': Decimal('1.5'),
                'aggressor_side': 'BUY',
            },
            {
                'ts_event': 1700000001 * 1_000_000_000,
                'ts_init': 1700000001 * 1_000_000_000,
                'price': Decimal('100.6'),
                'size': Decimal('2.0'),
                'aggressor_side': 'SELL',
            },
        ])
        
        mock_catalog.read_ticks.return_value = nautilus_ticks
        
        result = await source.fetch(
            start=1700000000,
            end=1700000010,
            node_id="tick:binance:BTC/USDT",
            interval=1,
        )
        
        assert 'ts' in result.columns
        assert 'price' in result.columns
        assert 'size' in result.columns
        assert 'side' in result.columns
        
        assert result['ts'].dtype == 'int64'
        assert result['price'].dtype == 'float64'
        assert result['size'].dtype == 'float64'
        
        assert result['side'].iloc[0] == 'buy'
        assert result['side'].iloc[1] == 'sell'
    
    @pytest.mark.asyncio
    async def test_fetch_quotes_converts_schema(self, source, mock_catalog):
        """fetch() converts Nautilus quote schema to QMTL schema."""
        nautilus_quotes = pd.DataFrame([
            {
                'ts_event': 1700000000 * 1_000_000_000,
                'ts_init': 1700000000 * 1_000_000_000,
                'bid_price': Decimal('100.0'),
                'ask_price': Decimal('100.5'),
                'bid_size': Decimal('10.0'),
                'ask_size': Decimal('8.0'),
            },
        ])
        
        mock_catalog.read_quotes.return_value = nautilus_quotes
        
        result = await source.fetch(
            start=1700000000,
            end=1700000010,
            node_id="quote:binance:BTC/USDT",
            interval=1,
        )
        
        assert 'ts' in result.columns
        assert 'bid' in result.columns
        assert 'ask' in result.columns
        assert 'bid_size' in result.columns
        assert 'ask_size' in result.columns
        
        assert result['bid'].iloc[0] == 100.0
        assert result['ask'].iloc[0] == 100.5
    
    @pytest.mark.asyncio
    async def test_fetch_handles_empty_result(self, source, mock_catalog):
        """fetch() handles empty results gracefully."""
        mock_catalog.read_bars.return_value = pd.DataFrame()
        
        result = await source.fetch(
            start=1700000000,
            end=1700000060,
            node_id="ohlcv:binance:BTC/USDT:1m",
            interval=60,
        )
        
        assert result.empty
    
    @pytest.mark.asyncio
    async def test_fetch_raises_on_catalog_error(self, source, mock_catalog):
        """fetch() raises RuntimeError on catalog errors."""
        mock_catalog.read_bars.side_effect = Exception("Catalog read failed")
        
        with pytest.raises(RuntimeError, match="Failed to fetch bar data"):
            await source.fetch(
                start=1700000000,
                end=1700000060,
                node_id="ohlcv:binance:BTC/USDT:1m",
                interval=60,
            )


def test_check_nautilus_available():
    """check_nautilus_available() handles missing dependency."""
    if NAUTILUS_AVAILABLE:
        # Should not raise if installed
        check_nautilus_available()
    else:
        # Should raise ImportError if not installed
        with pytest.raises(ImportError, match="nautilus_trader is required"):
            check_nautilus_available()


class TestTimestampConversion:
    """Test timestamp conversion between Nautilus and QMTL."""
    
    @pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")
    def test_nanoseconds_to_seconds_conversion(self):
        """Verify nanosecond → second conversion is correct."""
        source = NautilusCatalogDataSource(catalog=Mock())
        
        # Create Nautilus-style data with nanosecond timestamps
        nautilus_df = pd.DataFrame([
            {'ts_event': 1700000000 * 1_000_000_000, 'open': 100.0},
            {'ts_event': 1700000060 * 1_000_000_000, 'open': 101.0},
        ])
        
        result = source._normalize_to_qmtl(nautilus_df, 'bar')
        
        assert result['ts'].iloc[0] == 1700000000
        assert result['ts'].iloc[1] == 1700000060
        assert result['ts'].dtype == 'int64'


class TestDataTypeRouting:
    """Test routing to correct Nautilus catalog methods."""
    
    @pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")
    @pytest.mark.asyncio
    async def test_bar_routes_to_read_bars(self):
        """OHLCV node_id routes to catalog.read_bars()."""
        mock_catalog = Mock()
        mock_catalog.read_bars.return_value = pd.DataFrame()
        
        source = NautilusCatalogDataSource(catalog=mock_catalog)
        
        await source.fetch(
            start=1700000000,
            end=1700000060,
            node_id="ohlcv:binance:BTC/USDT:1m",
            interval=60,
        )
        
        mock_catalog.read_bars.assert_called_once()
        call_args = mock_catalog.read_bars.call_args
        assert call_args.kwargs['instrument'] == 'BTC/USDT'
        assert call_args.kwargs['bar_type'] == 'BTC/USDT-1m-LAST'
    
    @pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")
    @pytest.mark.asyncio
    async def test_tick_routes_to_read_ticks(self):
        """Tick node_id routes to catalog.read_ticks()."""
        mock_catalog = Mock()
        mock_catalog.read_ticks.return_value = pd.DataFrame()
        
        source = NautilusCatalogDataSource(catalog=mock_catalog)
        
        await source.fetch(
            start=1700000000,
            end=1700000010,
            node_id="tick:binance:BTC/USDT",
            interval=1,
        )
        
        mock_catalog.read_ticks.assert_called_once()
        call_args = mock_catalog.read_ticks.call_args
        assert call_args.kwargs['instrument'] == 'BTC/USDT'
    
    @pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")
    @pytest.mark.asyncio
    async def test_quote_routes_to_read_quotes(self):
        """Quote node_id routes to catalog.read_quotes()."""
        mock_catalog = Mock()
        mock_catalog.read_quotes.return_value = pd.DataFrame()
        
        source = NautilusCatalogDataSource(catalog=mock_catalog)
        
        await source.fetch(
            start=1700000000,
            end=1700000010,
            node_id="quote:binance:BTC/USDT",
            interval=1,
        )
        
        mock_catalog.read_quotes.assert_called_once()
        call_args = mock_catalog.read_quotes.call_args
        assert call_args.kwargs['instrument'] == 'BTC/USDT'


class TestNautilusSeamlessPresets:
    """Test Nautilus Seamless preset registration."""
    
    def test_nautilus_presets_registered(self):
        """Verify nautilus presets are registered."""
        from qmtl.runtime.sdk.seamless import SeamlessPresetRegistry
        
        # Trigger registration by importing
        import qmtl.runtime.io.seamless_presets  # noqa: F401
        
        # Check presets are available
        assert "nautilus.catalog" in SeamlessPresetRegistry._presets
        assert "nautilus.full" in SeamlessPresetRegistry._presets
    
    @pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")
    def test_nautilus_catalog_preset_creates_source(self, tmp_path):
        """Test nautilus.catalog preset creates NautilusCatalogDataSource."""
        from qmtl.runtime.sdk.seamless import SeamlessBuilder, SeamlessPresetRegistry
        
        # Create a minimal catalog directory
        catalog_path = tmp_path / "catalog"
        catalog_path.mkdir()
        
        builder = SeamlessBuilder()
        config = {"catalog_path": str(catalog_path)}
        
        result = SeamlessPresetRegistry.apply("nautilus.catalog", builder=builder, config=config)
        
        # Builder should have storage configured
        assert result.storage is not None
    
    @pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")
    def test_nautilus_full_preset_requires_exchange(self, tmp_path):
        """Test nautilus.full preset requires exchange_id."""
        from qmtl.runtime.sdk.seamless import SeamlessBuilder, SeamlessPresetRegistry
        
        catalog_path = tmp_path / "catalog"
        catalog_path.mkdir()
        
        builder = SeamlessBuilder()
        config = {"catalog_path": str(catalog_path)}
        
        # Should raise because exchange_id is missing
        with pytest.raises(KeyError, match="exchange_id"):
            SeamlessPresetRegistry.apply("nautilus.full", builder=builder, config=config)
    
    @pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")
    def test_nautilus_full_preset_creates_both_sources(self, tmp_path):
        """Test nautilus.full preset creates storage and live feed."""
        from qmtl.runtime.sdk.seamless import SeamlessBuilder, SeamlessPresetRegistry
        
        catalog_path = tmp_path / "catalog"
        catalog_path.mkdir()
        
        builder = SeamlessBuilder()
        config = {
            "catalog_path": str(catalog_path),
            "exchange_id": "binance",
            "symbols": ["BTC/USDT"],
            "timeframe": "1m",
        }
        
        result = SeamlessPresetRegistry.apply("nautilus.full", builder=builder, config=config)
        
        # Both storage and live should be configured
        assert result.storage is not None
        assert result.live is not None


@pytest.mark.contract
class TestNautilusCoreLoopContract:
    """Core Loop contract tests for Nautilus integration.
    
    These tests verify that Nautilus presets comply with QMTL's Core Loop principles:
    1. Single entry point (SeamlessPresetRegistry)
    2. World preset → Seamless auto-wiring
    3. Default-safe behavior (fail fast with clear messages)
    """
    
    def test_nautilus_presets_in_yaml_map(self):
        """Verify nautilus presets are registered in presets.yaml data_presets map.
        
        Core Loop requirement: world.data.presets[] must reference presets
        that exist in the Seamless preset map (YAML).
        """
        from qmtl.foundation.config import SeamlessConfig
        from qmtl.runtime.sdk.seamless_data_provider import _load_presets_document
        
        config = SeamlessConfig()
        presets_data, source = _load_presets_document(config)
        
        # Verify presets.yaml has data_presets section
        assert isinstance(presets_data, dict), "presets.yaml should be a dict"
        data_presets = presets_data.get("data_presets", {})
        
        # Check nautilus presets exist in the YAML map
        nautilus_presets = [k for k in data_presets.keys() if "nautilus" in k.lower()]
        assert len(nautilus_presets) >= 2, (
            f"Expected at least 2 nautilus presets in presets.yaml, found: {nautilus_presets}"
        )
        
        # Verify preset structure follows standard schema
        for preset_key in nautilus_presets:
            preset = data_presets[preset_key]
            assert "provider" in preset, f"Preset {preset_key} must have 'provider' block"
            assert "preset" in preset["provider"], f"Preset {preset_key} provider must have 'preset' name"
    
    def test_nautilus_preset_references_registry(self):
        """Verify YAML presets reference registered SeamlessPresetRegistry presets.
        
        Core Loop requirement: provider.preset in YAML must exist in 
        SeamlessPresetRegistry for auto-wiring to work.
        """
        from qmtl.foundation.config import SeamlessConfig
        from qmtl.runtime.sdk.seamless_data_provider import _load_presets_document
        from qmtl.runtime.sdk.seamless import SeamlessPresetRegistry
        
        # Ensure presets are registered
        import qmtl.runtime.io.seamless_presets  # noqa: F401
        
        config = SeamlessConfig()
        presets_data, _ = _load_presets_document(config)
        data_presets = presets_data.get("data_presets", {})
        
        nautilus_presets = [k for k in data_presets.keys() if "nautilus" in k.lower()]
        
        for preset_key in nautilus_presets:
            provider_block = data_presets[preset_key].get("provider", {})
            provider_preset = provider_block.get("preset")
            
            assert provider_preset in SeamlessPresetRegistry._presets, (
                f"YAML preset '{preset_key}' references '{provider_preset}' "
                f"which is not registered in SeamlessPresetRegistry. "
                f"Available: {list(SeamlessPresetRegistry._presets.keys())}"
            )
    
    def test_default_safe_missing_nautilus(self):
        """Verify nautilus preset fails fast with clear message when not installed.
        
        Core Loop requirement: Default-safe behavior should fail fast
        with actionable error message rather than silently degrading.
        """
        from qmtl.runtime.io.seamless_presets import NautilusPresetUnavailableError
        
        # When nautilus is not available, the error should be informative
        error = NautilusPresetUnavailableError("nautilus.catalog")
        
        assert "nautilus.catalog" in str(error)
        assert "uv pip install" in str(error) or "install" in str(error).lower()
        assert "Alternative" in str(error) or "alternative" in str(error).lower()
    
    def test_default_safe_missing_exchange_id(self):
        """Verify nautilus.full fails fast when exchange_id missing.
        
        Core Loop requirement: Required config must fail fast,
        not silently produce incomplete provider.
        """
        from qmtl.runtime.sdk.seamless import SeamlessPresetRegistry
        import qmtl.runtime.io.seamless_presets  # noqa: F401
        
        # Should raise clear error about missing exchange_id
        from qmtl.runtime.sdk.seamless import SeamlessBuilder
        builder = SeamlessBuilder()
        
        # This will fail at nautilus import if not installed, or at exchange_id check
        try:
            SeamlessPresetRegistry.apply("nautilus.full", builder=builder, config={})
            pytest.fail("Expected error for missing exchange_id or nautilus_trader")
        except (KeyError, ImportError) as e:
            # Either nautilus not installed or exchange_id missing - both are valid failures
            error_msg = str(e).lower()
            assert "exchange" in error_msg or "nautilus" in error_msg, (
                f"Error should mention 'exchange' or 'nautilus': {e}"
            )
    
    def test_world_data_preset_resolution_path(self):
        """Verify world → data_preset → provider chain works for nautilus.
        
        Core Loop requirement: Full resolution path from world.data.presets[]
        to SeamlessDataProvider must be functional.
        """
        from qmtl.foundation.config import SeamlessConfig
        from qmtl.runtime.sdk.world_data import _load_data_preset_spec
        
        # Should be able to load nautilus preset spec from YAML
        config = SeamlessConfig()
        
        # Try to load a nautilus preset spec
        spec = _load_data_preset_spec("ohlcv.nautilus.crypto.1m", seamless_config=config)
        
        assert spec.key == "ohlcv.nautilus.crypto.1m"
        assert spec.provider_name == "nautilus.catalog"
        assert spec.interval_ms == 60000
