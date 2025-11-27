"""
Utility: Convert PySR hall_of_fame.csv rows to a simple DAG spec JSON.

Assumptions
- hall_of_fame.csv columns: Complexity, Loss, Equation (PySR default)
- Sympy is available (PySR already pulls it in)

Outputs
- Writes `dag_specs.json` next to the HOF file by default.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from dataclasses import asdict

from qmtl.integrations.sr.pysr_adapter import load_pysr_hof_as_dags

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hof",
        type=Path,
        default=None,
        help="Path to hall_of_fame.csv (default: latest under outputs/*/)",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=20,
        help="Drop expressions whose DAG node_count exceeds this threshold.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: dag_specs.json next to HOF).",
    )
    args = parser.parse_args()

    hof_path = args.hof
    specs = load_pysr_hof_as_dags(
        hof_path=hof_path,
        outputs_base=Path("outputs"),
        max_nodes=args.max_nodes,
    )
    out_path = args.out
    if out_path is None:
        if hof_path is None:
            out_path = Path("outputs/latest_dag_specs.json")
        else:
            out_path = Path(hof_path).with_name("dag_specs.json")

    out_data = [asdict(s) for s in specs]
    out_path.write_text(json.dumps(out_data, indent=2))
    print(f"Saved {len(specs)} DAG specs to {out_path}")


if __name__ == "__main__":
    main()
