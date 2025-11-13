# Report CLI

The `qmtl report` command generates a simple performance report from a JSON file
containing a `returns` array.

```bash
qmtl report --from results.json --out report.md
```

The command computes standard metrics using
`qmtl.runtime.transforms.alpha_performance.alpha_performance_node` and writes them to a
Markdown report.

Metrics are emitted under the `alpha_performance.<metric>` namespace (for example,
`alpha_performance.sharpe` or `alpha_performance.max_drawdown`) to stay aligned with the
alpha_metrics envelope produced by WorldService. Unknown keys are safely ignored so the
parser can evolve without breaking the report CLI.
