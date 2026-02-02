# Refactor: Migrate from Pandas to Polars

## Context
The current codebase heavily relies on `pandas` for data manipulation, particularly within the IO layers (`qmtl/runtime/io`), SDK core (`qmtl/runtime/sdk`), and Examples. To improve performance (speed and memory usage) and type safety, we plan to migrate the dataframe implementation to `polars`.

## Impact Analysis
- **Affected Files**: ~76 files identified.
- **Key Modules**:
    - `qmtl/runtime/sdk/data_io.py`: Defines protocols (`DataFetcher`, `HistoryBackend`) returning `pd.DataFrame`.
    - `qmtl/runtime/io/`: Implementations like `ccxt_fetcher.py`, `binance_fetcher.py`.
    - `qmtl/runtime/sdk/world_data.py`: Generates synthetic data.
    - `qmtl/foundation/`: Schema validation.

## Migration Strategy
The migration will be executed in phases to maintain stability. We recommend a "Leaf-first" or "Core Interfaces" approach. Given the strong typing in `data_io.py`, changing the Core Protocols first is necessary, followed by implementations.

### Phase 1: Preparation & Dependencies
- [x] Add `polars` to `pyproject.toml` dependencies.
- [x] Add `polars` to `dev` dependencies (for testing).

### Phase 2: Core Protocols (`qmtl/runtime/sdk`)
- [x] Update `qmtl/runtime/sdk/data_io.py`:
    - Replace `import pandas as pd` with `import polars as pl`.
    - Update `DataFetcher.fetch` -> `pl.DataFrame`.
    - Update `HistoryBackend` methods -> `pl.DataFrame`.
    - Update `HistoryFetchResult` alias.
- [x] Update `qmtl/runtime/sdk/world_data.py`:
    - Refactor `_generate_demo_ohlcv_frame` to return `pl.DataFrame`.

### Phase 3: IO Implementations (`qmtl/runtime/io`)
Refactor the following to return `pl.DataFrame` instead of `pd.DataFrame`:
- [x] `qmtl/runtime/io/ccxt_fetcher.py` (OHLCV & Trades)
    - Remove `reset_index`, `drop_duplicates`.
    - Use `pl.DataFrame(rows).unique(subset=["ts"]).sort("ts")`.
- [x] `qmtl/runtime/io/binance_fetcher.py`
- [x] `qmtl/runtime/io/seamless_provider.py`
- [x] `qmtl/runtime/io/historyprovider.py`
- [x] `qmtl/runtime/io/nautilus_catalog_source.py`

### Phase 4: Core Logic & Validation
- [x] `qmtl/foundation/schema/validator.py`: Update validation logic for Polars schemas.
- [x] `qmtl/runtime/sdk/cache_view.py`: Update internal storage if it caches DataFrames.

### Phase 5: Examples & Scripts
- [x] Update examples in `examples/` and `qmtl/examples/` to work with Polars API (e.g., `.select`, `.filter` instead of `df[]` or `.loc`).

### Phase 6: Tests
- [x] Refactor `tests/` to use `pl.testing.assert_frame_equal`.
- [x] Update test fixtures to generate Polars DataFrames.

## Technical Guidelines
1.  **No Index**: Polars does not have an index. Ensure all DataFrames have an explicit `ts` (timestamp) column (integer seconds or `Datetime`).
    -   *Current pattern*: `df.set_index('ts')` (implicit in some places).
    -   *New pattern*: Operations must explicitly reference `on="ts"`.
2.  **Construction**:
    -   *Pandas*: `pd.DataFrame(list_of_dicts)`
    -   *Polars*: `pl.DataFrame(list_of_dicts)` (Efficient).
3.  **Sorting**:
    -   *Pandas*: `df.sort_values("ts")`
    -   *Polars*: `df.sort("ts")`
4.  **Deduplication**:
    -   *Pandas*: `df.drop_duplicates(subset=["ts"])`
    -   *Polars*: `df.unique(subset=["ts"])`
5.  **Types**:
    -   Ensure `ts` is consistently handled (e.g., `Int64` for unix timestamp or `Datetime` type). `qmtl` seems to use `int` (seconds) currently. Keep this consistent or move to `pl.Datetime` if beneficial.

## Questions / Risks
- **Nautilus Integration**: `scripts/benchmark_nautilus_integration.py` now uses polars for benchmarks; keep a boundary conversion helper on standby in case an upstream Nautilus API ever hard-requires pandas.
