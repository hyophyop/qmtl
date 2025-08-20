# Alpha Usage Tracking

This document describes the alpha usage tracking system that monitors which implemented alphas are actively used in strategy DAGs versus which remain unused.

## Overview

The alpha workflow in this repository follows this pattern:
1. Alpha ideas → refined by advanced models (GPT-5 Pro) → refined ideas implemented → usage tracking

The usage tracking system addresses the need to avoid unused alpha implementations by providing visibility into which alphas are actively used in strategies.

## Tools

### 1. `scripts/track_alpha_usage.py`

Main tracking script that analyzes alpha usage across the codebase.

**Usage:**
```bash
# Generate usage report
python scripts/track_alpha_usage.py

# Generate JSON format report  
python scripts/track_alpha_usage.py --format json

# Update alphadocs registry with usage information
python scripts/track_alpha_usage.py --update-registry

# Save report to file
python scripts/track_alpha_usage.py --output usage_report.txt
```

**Features:**
- Scans `strategies/nodes/indicators/` for available alpha implementations
- Analyzes `strategies/dags/` files for alpha usage in DAG definitions
- Detects indirect usage (e.g., alphas used within composite_alpha)
- Cross-references with `docs/alphadocs_registry.yml` for implementation status
- Updates registry with usage status

### 2. `scripts/list_unused_alphas.py`

Quick utility to identify unused alpha implementations.

**Usage:**
```bash
# List only unused alphas
python scripts/list_unused_alphas.py
```

**Exit codes:**
- `0`: All alphas are used
- `n`: Number of unused alphas found

### 3. Enhanced Registry Format

The `docs/alphadocs_registry.yml` now includes usage tracking fields:

```yaml
- doc: docs/alphadocs/ideas/gpt5pro/some-alpha-theory.md
  status: implemented
  modules:
  - strategies/nodes/indicators/some_alpha.py
  priority: gpt5pro
  tags: []
  usage_status: used|unused
  used_in_strategies:
  - strategy_name
  - indicator:composite_alpha
```

**New fields:**
- `usage_status`: Either "used" or "unused"
- `used_in_strategies`: List of strategies/indicators that use this alpha

## Usage Detection Logic

The system detects alpha usage through multiple methods:

1. **Direct DAG Usage**: Alpha nodes directly called in strategy DAG files
2. **Import Analysis**: Functions imported from alpha indicator modules
3. **Composite Usage**: Alphas used within other alpha implementations (e.g., composite_alpha)

**Detection patterns:**
- Function calls ending in `_node` (e.g., `acceptable_price_band_node()`)
- Import statements: `from .module import alpha_node`
- Cross-file analysis to track indirect usage

## Current Status Example

As of the latest scan:
- **Total Available Alpha Nodes**: 9
- **Total Used Alpha Nodes**: 7  
- **Unused Alpha Nodes**: 2

**Used alphas:**
- `composite_alpha` → used in `all_alpha_signal_dag`
- `acceptable_price_band` → used in `indicator:composite_alpha`
- `llrti` → used in `indicator:composite_alpha`
- `latent_liquidity_alpha` → used in `indicator:composite_alpha`
- `non_linear_alpha` → used in `indicator:composite_alpha`
- `order_book_clustering_collapse` → used in `indicator:composite_alpha`
- `quantum_liquidity_echo` → used in `indicator:composite_alpha`

**Unused alphas:**
- `gap_amplification`
- `tactical_liquidity_bifurcation`

## Integration with Development Workflow

### For Alpha Implementers

1. After implementing a new alpha, run usage tracking to verify it's properly registered
2. Consider integrating unused alphas into existing composite strategies
3. Use `--update-registry` to maintain accurate usage status

### For Strategy Developers

1. Review unused alphas when developing new strategies
2. Use the tracking system to identify available but underutilized alphas
3. Monitor usage patterns to optimize strategy composition

### For Project Maintenance

1. Regularly run usage tracking to identify technical debt (unused implementations)
2. Consider deprecating long-unused alphas after careful review
3. Use usage data to prioritize alpha development efforts

## Command Examples

```bash
# Daily usage check
python scripts/list_unused_alphas.py

# Comprehensive analysis with registry update
python scripts/track_alpha_usage.py --update-registry --output daily_usage_report.txt

# JSON export for automated processing
python scripts/track_alpha_usage.py --format json --output usage_data.json

# Check usage before implementing new alpha
python scripts/track_alpha_usage.py | grep -A 10 "UNUSED ALPHAS"
```

## Testing

Usage tracking functionality is tested in `strategies/tests/test_alpha_usage_tracking.py`:

```bash
cd /path/to/repo
PYTHONPATH=. python strategies/tests/test_alpha_usage_tracking.py
```

Tests cover:
- Basic tracking functionality
- Usage detection accuracy
- Registry update operations
- Output format validation