# Linearity & Alpha Metrics Complexity Plan

## Background and Goals

- This document summarizes the design work for improving the complexity of metric/statistical routines as proposed in issue `#1552`.
- The goal is to refactor representative functions that had radon CC grade C by splitting the common computation flow (data prep → computation → aggregation) into template/strategy components to improve readability, testability, and reuse.
- Main targets:
  - `qmtl/runtime/transforms/linearity_metrics.py: equity_linearity_metrics_v2`
  - `qmtl/runtime/helpers/runtime.py: compute_alpha_performance_summary`
  - `qmtl/services/worldservice/decision.py: augment_metrics_with_linearity`

## Shared Design Principles

- **Template Method pattern**
  - Break complex metric calculations into:
    - Input normalization/data preparation
    - Core statistics (slope, R², drawdown, etc.)
    - Result aggregation/scoring
  - The top-level function fixes the flow and delegates details to helpers/strategies.

- **Strategy pattern**
  - Separate per-metric/per-scenario logic into strategy objects.
  - The service layer focuses on selecting and composing strategies instead of directly depending on low-level statistical implementations.

- **Reusable statistical helpers**
  - Extract OLS, t-statistics, volatility/drawdown, and summary statistics into small helper functions that can be reused across modules.
  - Keep helpers as close to pure functions as possible to simplify unit testing and future refactors.

## Refactoring equity_linearity_metrics_v2

### Original issues

- A single function interleaved:
  - Orientation handling (up/down) and optional log transform
  - OLS regression and t-statistic computation
  - TVR, persistence based on time/new highs, and normalized drawdown
  - Final score aggregation from all components
- As a result, CC climbed to C(19).

### Improved structure

- Input normalization
  - `_prepare_oriented_series`  
    - Normalizes the `pnl` series based on `orientation` (up/down) and `use_log`.
    - Falls back to the original space when log-transform is not applicable (non-positive values).

- Statistical components
  - `_trend_components`  
    - Uses `_ols_slope_r2_t` to get `(slope, r2, t_stat)` and accepts only positive slopes as `r2_up`.
    - Computes rank correlation via `_spearman_rho` and exposes `t_slope_sig` as a separate component.
  - `_tvr_multi_scale`  
    - Downsamples the series at multiple scales (`scales=(1, 5, 20)` etc.) via `_coarse` and applies `_variation_ratio`.
    - Combines TVR values via geometric mean.
  - `_persistence_components`  
    - Uses `_time_under_water` to obtain `tuw` and derives `nh_frac(=1 - tuw)`.
  - `_normalized_drawdown`  
    - Normalizes drawdown (`mdd_norm`) using `_max_drawdown` and `net_gain`.

- Score aggregation strategy
  - `_LinearityComponents` dataclass  
    - Groups `r2_up`, `spearman_rho`, `tvr`, `tuw`, `nh_frac`, `mdd_norm`, `net_gain`, etc.
  - `_HarmonicMeanLinearityStrategy`  
    - First checks directional consistency (whether raw `raw_gain` is aligned with `orientation`).
    - Aggregates four components—trend (√(r2_up × ρ⁺)), smooth (TVR), persistence (nh_frac), and DD penalty (1/(1 + mdd_norm))—into a harmonic mean after clamping into `(0, 1]`.
  - `equity_linearity_metrics_v2`  
    - Becomes a thin orchestrator that wires together the template and strategy, improving CC to grade A.

## Refactoring compute_alpha_performance_summary

### Original issues

- A single function was responsible for:
  - NaN filtering
  - Branching between realistic costs vs fixed `transaction_cost`
  - Excess return, Sharpe, drawdown, and ratio calculations
  - Adding the alpha_performance prefix and merging execution_* metrics
- This made the function hard to read, test, and reuse, with CC at C(13).

### Improved structure

- Input cleanup and cost handling
  - `_clean_returns`  
    - Filters out NaNs and casts values to `float`.
  - `_net_returns_and_execution_metrics`  
    - Applies either:
      - Realistic costs: `adjust_returns_for_costs` + `calculate_execution_metrics`
      - Simple costs: deducts `transaction_cost` per period
    - Returns both `net_returns` and `execution_metrics` in one place.

- Core alpha metrics
  - `_excess_returns` / `_sharpe_ratio`
  - `_alpha_core_metrics`  
    - Computes `sharpe`, `max_drawdown`, `win_ratio`, `profit_factor`, `car_mdd`, `rar_mdd`.

- Top-level template
  - `compute_alpha_performance_summary` now focuses on:
    - Cleaning inputs → applying costs → computing core metrics → adding prefixes/merging execution metrics
  - The resulting schema (`alpha_performance.<metric>`, `execution_<metric>`) remains unchanged, while CC improves to grade A.

## WorldService: Refactoring augment_metrics_with_linearity

### Original issues

- The service-level function `augment_metrics_with_linearity` handled:
  - Materializing per-strategy equity series
  - Computing and injecting v1/v2 linearity metrics
  - Computing and injecting per-strategy alpha metrics
  - Building a portfolio equity and injecting portfolio-level linearity/alpha metrics
- The mixed responsibilities made it hard to extend with new linearity/alpha variants.

### Improved structure

- Strategy-style helper
  - `_LinearityMetricsAugmentor` class
    - `augment(metrics, series)`  
      - Acts as the template for what used to be `augment_metrics_with_linearity`.
      - Copies the input metric map and then injects per-strategy and portfolio metrics in sequence.
    - `_extract_equity_series`  
      - Uses `_materialize_equity_curve` to materialize per-strategy equity, then injects v1/v2 linearity and alpha metrics into the slots.
    - `_augment_with_portfolio_metrics`  
      - Builds a portfolio equity and injects linearity/alpha metrics into per-strategy slots.
  - The global function `augment_metrics_with_linearity` is now a thin wrapper around `_LinearityMetricsAugmentor().augment(...)`, preserving the existing service API contract.

## Radon and Verification Strategy

- radon CC goals
  - `equity_linearity_metrics_v2`: C → A
  - `compute_alpha_performance_summary`: C → A
  - `augment_metrics_with_linearity`: keep grade A but move the heavy lifting into `_LinearityMetricsAugmentor` to make future extensions easier.
- Testing
  - Linearity metrics:
    - `tests/qmtl/runtime/transforms/test_equity_linearity.py`
    - `tests/qmtl/runtime/transforms/test_equity_linearity_v2.py`
  - Alpha metrics:
    - `tests/qmtl/runtime/test_alpha_metrics.py`
  - WorldService wiring:
    - `tests/qmtl/services/worldservice/test_linearity_wiring.py`
- Performance and numerical correctness
  - Reuse the existing test suite to perform numerical regression checks.
  - Since we refactored existing OLS/statistics into helpers/templates, algorithmic complexity remains the same while readability and reuse improve.

## Future Extensions

- When adding new linearity/alpha metrics:
  - Extend helpers/strategies in the transforms/helpers layers.
  - Adjust `_LinearityMetricsAugmentor` or similar strategy-style helpers in the WorldService layer while keeping the external service contract stable.
- From a radon perspective:
  - Reuse the template/strategy structure for new metrics to prevent a new wave of CC grade C functions.
  - Tie back into periodic radon snapshots (for example, the 2025-11-14 snapshot) to catch complexity regressions early.

