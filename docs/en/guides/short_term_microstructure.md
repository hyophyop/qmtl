# Short-Term Microstructure Filters

Short-horizon order-book strategies benefit from combining **microprice**,
**depth imbalance**, and **queue priority**. This guide introduces the new
runtime nodes that expose these signals and demonstrates how to gate an entry
decision.

## Microprice + Imbalance Node

Use `microprice_imbalance()` to parse an order-book snapshot and emit both the
weighted microprice and the signed imbalance across the top `N` levels.

- `top_levels` controls how many tiers contribute to the imbalance ratio.
- `epsilon` stabilises the denominator whenever both sides are empty.
- The returned node yields a payload with `"microprice"` and `"imbalance"`
  keys, making it straightforward to fan out into downstream nodes.

## Priority Index

`priority_index()` normalises queue metadata into a `[0, 1]` score, where `1`
means the order is at the front of the book. The source snapshots must include
`queue_rank` and `queue_size` values (either scalars or parallel sequences).
Invalid or missing entries are converted to `None` so downstream logic can drop
them safely.

## Conditional Entry Filter

`conditional_entry_filter()` wires the microprice metrics and the priority index
into a boolean gate. The node checks that:

1. a microprice reading is available (and optionally within bounds),
2. the imbalance lies inside the specified `(min, max)` window, and
3. the priority index respects the configured limits.

When the priority node emits a sequence, choose `priority_mode="any"` to allow
at least one queue position through, or `"all"` to require every entry to pass
the bounds. The defaults keep moderate imbalances (±0.25) and prefer front-half
queue positions (`0.6–1.0`).

## Example Pipeline

The `examples/microprice_priority_strategy.py` module assembles the nodes into a
minimal strategy gate:

```python
from examples.microprice_priority_strategy import build_pipeline

artifacts = build_pipeline()
entry_gate = artifacts.entry_gate
# Feed order-book snapshots + queue metadata via CacheView
```

Running the module as a script (`python examples/microprice_priority_strategy.py`)
prints the simulated microprice, imbalance, priority index, and the resulting
`allow_entry` flag. Use this scaffold when integrating the indicators into a
full DAG.
