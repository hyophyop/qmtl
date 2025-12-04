---
title: "Quickstart"
tags:
  - getting-started
  - quickstart
  - tutorial
author: "QMTL Team"
last_modified: 2025-12-01
---

# Quickstart

Follow this guide to write and submit your first strategy **in 10 minutes**.

## Prerequisites

- Python 3.11+
- QMTL installed (`pip install qmtl` or `uv pip install -e .[dev]`)

## Step 1: Write a Strategy (3 min)

Create a file `my_strategy.py`:

```python
from qmtl.sdk import Strategy, StreamInput, Node, Runner, Mode
import pandas as pd

class MomentumStrategy(Strategy):
    """Simple momentum strategy: buy signal if recent returns are positive"""
    
    def setup(self):
        # 1-minute candle price data, need last 30
        price = StreamInput(
            tags=["BTC", "price"],
            interval="1m",
            period=30
        )
        
        def compute_signal(view) -> pd.DataFrame:
            # Get close price data
            df = view.as_frame(price, columns=["close"])
            
            # Calculate 5-minute momentum
            momentum = df["close"].pct_change().rolling(5).mean()
            
            # Buy (1) if momentum > 0, else hold (0)
            signal = (momentum > 0).astype(int)
            
            return pd.DataFrame({"signal": signal})
        
        signal_node = Node(
            input=price,
            compute_fn=compute_signal,
            name="momentum_signal"
        )
        
        self.add_nodes([price, signal_node])


if __name__ == "__main__":
    # Submit strategy
    result = Runner.submit(
        MomentumStrategy,
        world="quickstart_demo",
        mode=Mode.BACKTEST
    )
    print(result)
```

## Step 2: Run the Strategy (1 min)

```bash
python my_strategy.py
```

## Step 3: Check Results (1 min)

On success, you'll receive results like:

```python
{
  "strategy_id": "momentum_btc_1m_abc123",
  "status": "valid",              # valid | invalid | pending | rejected
  "world": "quickstart_demo",
  "mode": "backtest",
  "downgraded": false,            # True if forced into safe compute-only
  "downgrade_reason": null,       # e.g., "missing_as_of" when backtest inputs are incomplete
  "safe_mode": false,
  "ws": {                         # WorldService is the SSOT for decisions/activations
    "decision": { "world_id": "quickstart_demo", "effective_mode": "validate", "etag": "..." },
    "activation": { "strategy_id": "momentum_btc_1m_abc123", "weight": 0.10, "active": true },
    "metrics": { "sharpe": 1.45, "max_drawdown": -0.08, "win_rate": 0.55, "profit_factor": 1.32 },
    "threshold_violations": [],
    "rejection_reason": null
  },
  "precheck": {                   # Local ValidationPipeline reference only
    "status": "passed",
    "violations": [],
    "metrics": { "sharpe": 1.4, "max_drawdown": -0.09 }
  }
}
```

The CLI can emit the same WS/Precheck-separated JSON with:

```bash
qmtl submit strategies.momentum:MomentumStrategy --world quickstart_demo --mode backtest --output json
```

---

## Understanding: What Happened?

```mermaid
sequenceDiagram
    participant You as User
    participant SDK as Runner.submit()
    participant GW as Gateway
    participant WS as WorldService
    
    You->>SDK: Submit MomentumStrategy
    SDK->>SDK: Serialize DAG
    SDK->>GW: POST /strategies
    GW->>GW: Load history data
    GW->>GW: Execute backtest
    GW->>WS: Request evaluation
    WS->>WS: Policy validation (Sharpe, MDD, etc.)
    WS-->>GW: Evaluation result
    GW-->>SDK: SubmitResult
    SDK-->>You: Print result
```

**What the system automatically did:**
1. Converted strategy code to DAG (computation graph)
2. Auto-loaded required history data
3. Executed backtest (market situation replay)
4. Calculated performance metrics
5. Validated against world policy criteria
6. Generated improvement hints

---

## Next Step Guides

### A. Making a Valid Strategy

Improve strategy based on `improvement_hints`:

```python
# Use longer data period
price = StreamInput(
    tags=["BTC", "price"],
    interval="1m",
    period=60  # Increased 30 → 60
)

# More sophisticated signal logic
def compute_signal(view):
    df = view.as_frame(price, columns=["close", "volume"])
    
    # Price momentum
    price_mom = df["close"].pct_change().rolling(10).mean()
    
    # Volume confirmation (only when volume increasing)
    vol_increase = df["volume"].pct_change() > 0
    
    # Buy only when both conditions met
    signal = ((price_mom > 0) & vol_increase).astype(int)
    
    return pd.DataFrame({"signal": signal})
```

### B. Promote to Paper Mode

When backtest performance meets criteria:

```python
result = Runner.submit(
    MomentumStrategy,
    world="quickstart_demo",
    mode=Mode.PAPER  # Virtual trading with real-time data
)
```

!!! note "As-Is / To-Be: Auto Promotion"
    **As-Is (Current):**
    - User must explicitly resubmit with `mode=Mode.PAPER`
    
    **To-Be (Target):**
    - Auto-promote to Paper mode when backtest passes
    - User just checks results

### C. Performance Monitoring

!!! note "As-Is / To-Be: Performance Query"
    **As-Is (Current):**
    ```bash
    # Check status via CLI
    qmtl status --world quickstart_demo
    ```
    
    **To-Be (Target):**
    ```python
    # Subscribe to real-time stream in Python
    Runner.subscribe(world="quickstart_demo", on_update=print)
    ```
    
    - Check real-time performance/rank/contribution in dashboard UI
    - Auto-receive promotion/demotion notifications

---

## Using the CLI

### Submit Strategy

```bash
# Submit file directly
qmtl submit my_strategy.py --world quickstart_demo

# Specify mode
qmtl submit my_strategy.py --world quickstart_demo --mode paper
```

### Check Status

```bash
# Query world status
qmtl world info quickstart_demo

# Check my strategy status
qmtl status --strategy momentum_btc_1m_abc123
```

!!! note "As-Is / To-Be: CLI Simplification"
    **As-Is (Current):**
    ```bash
    qmtl submit my_strategy.py --world demo --gateway-url http://localhost:8000
    ```
    
    **To-Be (Target):**
    ```bash
    qmtl submit my_strategy.py  # Auto-use default world and gateway
    ```

---

## Common Troubleshooting

### "No returns produced" Error

```
Error: No returns produced. Cannot validate strategy.
```

**Cause:** Strategy doesn't generate returns data

**Solution:** 
```python
# Include returns column in compute_fn
def compute_signal(view):
    df = view.as_frame(price, columns=["close"])
    returns = df["close"].pct_change()
    signal = (returns.rolling(5).mean() > 0).astype(int)
    return pd.DataFrame({
        "signal": signal,
        "returns": returns  # This column is required
    })
```

!!! note "As-Is / To-Be: auto_returns"
    **As-Is (Current):**
    - User must explicitly compute `returns` column
    
    **To-Be (Target):**
    - Auto-derive from price data with `auto_returns=True` option
    - Or auto-compute in `StreamInput`

### Gateway Connection Failed

```
Error: Cannot connect to Gateway at http://localhost:8000
```

**Solution:**
```bash
# Start Gateway server
qmtl gateway

# Or verify in another terminal
curl http://localhost:8000/health
```

### No Data Error

```
Error: No data available for tags=['BTC', 'price']
```

**Solution:** Verify data source for those tags is configured

```bash
# Query available data tags
qmtl data list-tags
```

---

## Next Steps

- Learn strategy improvement cycle → [User Workflow](workflow.md)
- Write more complex strategies → [SDK Tutorial](../guides/sdk_tutorial.md)
- Understand architecture → [Architecture Overview](../architecture/README.md)
