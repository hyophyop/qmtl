from __future__ import annotations

"""Validate SDK layer dependencies to prevent upward imports.

Rules enforced:
- Core SDK modules (cache/backfill/data_io/history_provider_facade/etc.) must
  not import node implementations.
"""

import argparse
from typing import Iterable, Sequence

from grimp import build_graph

CORE_PREFIXES: tuple[str, ...] = (
    "qmtl.runtime.sdk.auto_backfill",
    "qmtl.runtime.sdk.backfill_engine",
    "qmtl.runtime.sdk.cache",
    "qmtl.runtime.sdk.cache_backfill",
    "qmtl.runtime.sdk.cache_context",
    "qmtl.runtime.sdk.cache_reader",
    "qmtl.runtime.sdk.cache_ring_buffer",
    "qmtl.runtime.sdk.cache_view",
    "qmtl.runtime.sdk.cache_view_tools",
    "qmtl.runtime.sdk.data_io",
    "qmtl.runtime.sdk.history_coverage",
    "qmtl.runtime.sdk.history_provider_facade",
)

NODE_PREFIXES: tuple[str, ...] = (
    "qmtl.runtime.sdk.nodes",
    "qmtl.runtime.sdk.node",
)


def _is_under(module: str, prefixes: Sequence[str]) -> bool:
    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)


def _find_violations(modules: Iterable[str], edges: dict[str, set[str]]) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for source in modules:
        if not _is_under(source, CORE_PREFIXES):
            continue
        for target in edges.get(source, ()):
            if _is_under(target, NODE_PREFIXES):
                violations.append((source, target))
    return sorted(violations)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SDK layer dependencies.")
    parser.add_argument(
        "--package",
        default="qmtl",
        help="Root package to analyze (default: qmtl)",
    )
    args = parser.parse_args()

    graph = build_graph(args.package)
    modules = list(graph.modules)
    edges = {m: set(graph.find_modules_directly_imported_by(m)) for m in modules}

    violations = _find_violations(modules, edges)
    if violations:
        print("Layer violations detected (core -> nodes):")
        for source, target in violations:
            print(f"- {source} -> {target}")
        return 1

    print("Layer check passed: no core->nodes imports detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
