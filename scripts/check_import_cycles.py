from __future__ import annotations

"""Check Python import cycles against a recorded baseline.

This script builds an import graph using grimp and detects strongly
connected components (including self-loops). It fails if new cycles are
introduced compared to the saved baseline.
"""

import argparse
import json
from pathlib import Path
from typing import Iterable, Sequence

from grimp import build_graph


def _tarjan_cycles(modules: list[str], edges: dict[str, set[str]]) -> list[list[str]]:
    """Return strongly connected components that form cycles."""

    index = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    onstack: set[str] = set()
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        onstack.add(v)

        for w in sorted(edges.get(v, ())):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in onstack:
                lowlink[v] = min(lowlink[v], indices[w])

        if lowlink[v] == indices[v]:
            component: list[str] = []
            while True:
                w = stack.pop()
                onstack.remove(w)
                component.append(w)
                if w == v:
                    break
            sccs.append(component)

    for v in sorted(modules):
        if v not in indices:
            strongconnect(v)

    cycles: list[list[str]] = []
    for comp in sccs:
        if len(comp) > 1:
            cycles.append(sorted(comp))
            continue
        node = comp[0]
        if node in edges.get(node, set()):
            cycles.append([node])
    return sorted(cycles, key=lambda c: (len(c), c))


def compute_cycles(package: str) -> list[list[str]]:
    graph = build_graph(package)
    modules = list(graph.modules)
    edges = {m: set(graph.find_modules_directly_imported_by(m)) for m in modules}
    return _tarjan_cycles(modules, edges)


def load_baseline(path: Path) -> list[list[str]]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "cycles" in data:
        return [sorted(c) for c in data.get("cycles", [])]
    if isinstance(data, list):
        return [sorted(c) for c in data]
    raise ValueError(f"Unrecognized baseline format in {path}")


def save_baseline(path: Path, package: str, cycles: list[list[str]]) -> None:
    payload = {"package": package, "cycles": cycles}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def cycles_as_set(cycles: Iterable[Sequence[str]]) -> set[tuple[str, ...]]:
    return {tuple(c) for c in cycles}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check import cycles against a stored baseline."
    )
    parser.add_argument(
        "--package",
        default="qmtl",
        help="Root package to analyze (default: qmtl)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path(__file__).resolve().parent / "import_cycles_baseline.json",
        help="Path to baseline JSON file (default: scripts/import_cycles_baseline.json)",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write current cycles to the baseline file and exit.",
    )
    args = parser.parse_args()

    cycles = compute_cycles(args.package)

    if args.write_baseline:
        save_baseline(args.baseline, args.package, cycles)
        print(
            f"Baseline written to {args.baseline} "
            f"({len(cycles)} cycle components recorded)"
        )
        return 0

    if not args.baseline.exists():
        print(f"Baseline file {args.baseline} not found. Run with --write-baseline.")
        return 1

    baseline_cycles = load_baseline(args.baseline)
    current_set = cycles_as_set(cycles)
    baseline_set = cycles_as_set(baseline_cycles)

    new_cycles = current_set - baseline_set
    resolved_cycles = baseline_set - current_set

    if new_cycles:
        print("Detected new import cycles (not in baseline):")
        for cycle in sorted(new_cycles):
            print(f"- {list(cycle)}")
        if resolved_cycles:
            print("\nResolved cycles:")
            for cycle in sorted(resolved_cycles):
                print(f"- {list(cycle)}")
        return 1

    print(
        f"No new cycles detected. "
        f"Current={len(current_set)}, baseline={len(baseline_set)}, "
        f"resolved={len(resolved_cycles)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
