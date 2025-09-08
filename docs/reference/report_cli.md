# Report CLI

The `qmtl report` command generates a simple performance report from a JSON file
containing a `returns` array.

```bash
qmtl report --from results.json --out report.md
```

The command computes standard metrics using
`qmtl.transforms.alpha_performance.alpha_performance_node` and writes them to a
Markdown report.
