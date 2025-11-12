---
title: "Layer-Based Template System Quick Start Guide"
tags:
  - guide
  - templates
  - layers
  - quickstart
author: "QMTL Team"
last_modified: 2025-10-18
---

{{ nav_links() }}

# Layer-Based Template System Quick Start Guide

This guide explains how to get started quickly with QMTL's new layer‑based
template system.

## Overview

The layer system lets you assemble each stage of a strategy (data supply,
signal generation, execution, brokerage) independently and compose them as
needed.

### Available layers

| Layer | Description | Depends |
|--------|------|--------|
| **data** | Data ingestion/sourcing | none |
| **signal** | Alpha generation and transforms | data |
| **execution** | Order execution and management | signal |
| **brokerage** | Exchange integration | execution |
| **monitoring** | Observability and metrics | none |

### Presets

| Preset | Layers | Use |
|--------|--------|------|
| **minimal** | data, signal | backtesting, research |
| **research** | data, signal, monitoring | alpha research and analysis |
| **production** | data, signal, execution, brokerage, monitoring | live trading |
| **execution** | execution, brokerage | execution for external signals |

---

## Quick start

### 1. Create a project from a preset

```bash
# List available presets
qmtl project list-presets

# Create a minimal project
qmtl project init --path my_strategy --preset minimal

# Create a production project
qmtl project init --path my_prod --preset production
```

### 2. Generated project layout

```
my_strategy/
├── .gitignore              # git ignores
├── qmtl.yml                # QMTL config
├── strategy.py             # strategy entry point
├── layers/                 # layers directory
│   ├── __init__.py
│   ├── data/               # data layer
│   │   ├── __init__.py
│   │   ├── providers.py    # data provider export
│   │   └── stream_input.py # StreamInput implementation
│   └── signal/             # signal layer
│       ├── __init__.py
│       ├── strategy.py     # strategy export
│       └── single_indicator.py  # single-indicator strategy
└── tests/                  # tests directory
    └── test_strategy.py
```

### 3. Add layers

You can add layers to an existing project:

```bash
cd my_strategy

# Add monitoring layer
qmtl project add-layer monitoring

# Add execution layer (requires signal layer)
qmtl project add-layer execution
```

### 4. Inspect metadata and validate structure

```bash
# Show available layers and templates
qmtl project list-layers --show-templates

# Validate project structure
qmtl project validate --path my_strategy
```

---

## Layer details

### Data layer

Provides data inputs.

**Templates:**
- `stream_input.py`: basic StreamInput
- `ccxt_provider.py`: CCXT data provider

**Usage:**

```python
# import from layers/data/providers.py
from layers.data.providers import get_data_provider

# create data stream
data_stream = get_data_provider()
```

**Customizing:**

```python
# layers/data/custom_provider.py
from qmtl.runtime.sdk import StreamInput

def create_custom_stream():
    return StreamInput(
        interval="60s",
        period=50,
        name="custom_stream",
    )
```

### Signal layer

Generates signals.

**Templates:**
- `single_indicator.py`: single‑indicator strategy
- `multi_indicator.py`: multi‑indicator strategy

**Usage:**

```python
# import from layers/signal/strategy.py
from layers.signal.strategy import create_strategy

# build strategy
strategy = create_strategy()
```

**Customizing:**

Modify template(s) to add indicators and logic:

```python
# layers/signal/my_strategy.py
from qmtl.runtime.sdk import Strategy, Node
from qmtl.runtime.indicators import ema, rsi

class MyStrategy(Strategy):
    def setup(self):
        from layers.data.providers import get_data_provider
        
        price = get_data_provider()
        ema_node = ema(price, period=20)
        rsi_node = rsi(price, period=14)
        
        # custom signal logic
        def my_signal(view):
            # ... signal generation logic ...
            pass
        
        signal = Node(input=[ema_node, rsi_node], compute_fn=my_signal)
        self.add_nodes([price, ema_node, rsi_node, signal])
```

### Execution layer

Handles order execution.

**Templates:**
- `nodeset.py`: NodeSet‑based execution pipeline

**Usage:**

```python
from layers.execution.nodeset import attach_execution_to_strategy

# attach execution layer to strategy
attach_execution_to_strategy(strategy, signal_node)
```

### Brokerage layer

Handles exchange integration.

**Templates:**
- `ccxt_binance.py`: Binance integration

**Usage:**

```python
from layers.brokerage.ccxt_binance import create_broker

# Create broker (testnet)
broker = create_broker(testnet=True)

# Place an order
broker.place_order(
    symbol="BTC/USDT",
    side="buy",
    amount=0.001,
)
```

### Monitoring layer

Collects metrics.

**Templates:**
- `metrics.py`: basic metrics collection

**Usage:**

```python
from layers.monitoring.metrics import get_metrics_collector

collector = get_metrics_collector()

# Record a signal
collector.record_signal("BUY", strength=0.8)

# Record a trade
collector.record_trade("BTC/USDT", "buy", 0.001, 50000)

# Record performance
collector.record_performance("sharpe_ratio", 1.5)

# Retrieve metrics
metrics = collector.get_metrics()
```

---

## Advanced usage

### 1. Select layers explicitly

Choose layers directly instead of presets:

```bash
# Data + signal only
qmtl project init --path my_custom --layers data,signal

# Dependency auto‑resolution (execution includes data,signal)
qmtl project init --path my_exec --layers execution
```

### 2. List available layers

```bash
qmtl project list-layers
```

### 3. Validate the project

Verify that the generated structure is correct:

```bash
# TODO: to be added later
qmtl project validate
```

---

## Migration from legacy templates

The legacy `--strategy` switch still works but is deprecated:

```bash
# Legacy (deprecated)
qmtl project init --path old_style --strategy general
# Warning: --strategy is deprecated, use --preset instead

# New (recommended)
qmtl project init --path new_style --preset minimal
```

### Template → preset mapping

| Legacy template | New preset |
|-------------|-----------|
| `general` | `minimal` |
| `single_indicator` | `minimal` |
| `multi_indicator` | `minimal` |
| `branching` | `research` |
| `state_machine` | `research` |

---

## Running the strategy

Execute the generated `strategy.py`:

```bash
cd my_strategy

# Offline mode (no Gateway)
python strategy.py

# Production mode (requires Gateway)
# after changing strategy.py to call Runner.run():
python strategy.py
```

---

## Troubleshooting

### Import errors

If imports between layers fail, update PYTHONPATH:

```bash
export PYTHONPATH=/path/to/my_strategy:$PYTHONPATH
python strategy.py
```

### Layer dependency errors

If an add‑layer command fails due to missing dependencies, add the required layers first:

```bash
# EXECUTION requires SIGNAL
qmtl project add-layer signal
qmtl project add-layer execution
```

### Editing templates

Templates are intended to be modified—customize them as needed for your project.

---

## Next steps

- Review [Layered Template System Architecture](../architecture/layered_template_system.md)
- Learn the [Strategy Development Workflow](strategy_workflow.md)
- Follow the [SDK Tutorial](sdk_tutorial.md)

---

## References

- [Architecture Overview](../architecture/README.md)
- [Layered Template System Architecture](../architecture/layered_template_system.md)
- [Exchange Node Sets](../architecture/exchange_node_sets.md)
- [SDK Tutorial](sdk_tutorial.md)

---

**Document version**: 1.0  
**Last reviewed**: 2025-10-18
