#!/usr/bin/env python3
"""Track alpha usage across strategy DAGs and compare with implemented alphas."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency error
    print(f"PyYAML required: {exc}")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "alphadocs_registry.yml"
STRATEGIES_DIR = ROOT / "strategies"
INDICATORS_DIR = STRATEGIES_DIR / "nodes" / "indicators"


class AlphaUsageTracker:
    """Track which alpha nodes are used in strategy DAGs."""

    def __init__(self):
        self.implemented_alphas: dict[str, dict] = {}
        self.used_alphas: dict[str, list[str]] = {}
        self.alpha_node_files: dict[str, str] = {}

    def load_implemented_alphas(self) -> None:
        """Load implemented alpha information from registry."""
        if not REGISTRY.exists():
            return

        data = yaml.safe_load(REGISTRY.read_text())
        for entry in data or []:
            if entry.get("status") == "implemented":
                modules = entry.get("modules", [])
                alpha_modules = [
                    m for m in modules 
                    if m.startswith("strategies/nodes/indicators/")
                ]
                if alpha_modules:
                    doc_name = entry["doc"]
                    alpha_name = self._extract_alpha_name(doc_name)
                    self.implemented_alphas[alpha_name] = {
                        "doc": doc_name,
                        "modules": alpha_modules,
                        "priority": entry.get("priority", "normal"),
                        "tags": entry.get("tags", [])
                    }

    def _extract_alpha_name(self, doc_path: str) -> str:
        """Extract alpha name from documentation path."""
        path = Path(doc_path)
        name = path.stem
        # Convert various naming patterns to consistent format
        return name.replace("-", "_").replace(" ", "_").lower()

    def scan_alpha_node_files(self) -> None:
        """Scan indicator files to map function names to files."""
        if not INDICATORS_DIR.exists():
            return

        for py_file in INDICATORS_DIR.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            
            try:
                content = py_file.read_text()
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.endswith("_node"):
                        alpha_name = node.name.replace("_node", "")
                        self.alpha_node_files[alpha_name] = str(py_file.relative_to(ROOT))
            except Exception:
                # Skip files that can't be parsed
                continue

    def scan_strategy_usage(self) -> None:
        """Scan strategy DAG files for alpha node usage."""
        dag_dir = STRATEGIES_DIR / "dags"
        if not dag_dir.exists():
            return

        # Scan DAG files
        for py_file in dag_dir.glob("**/*.py"):
            if py_file.name.startswith("__"):
                continue

            strategy_name = py_file.stem
            used_in_strategy = self._extract_alpha_usage(py_file)
            if used_in_strategy:
                for alpha in used_in_strategy:
                    if alpha not in self.used_alphas:
                        self.used_alphas[alpha] = []
                    self.used_alphas[alpha].append(strategy_name)

        # Also scan indicator files themselves for internal alpha usage
        # This helps detect when one alpha uses another (like composite_alpha)
        for py_file in INDICATORS_DIR.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
                
            file_name = py_file.stem
            used_in_file = self._extract_alpha_usage(py_file)
            if used_in_file:
                for alpha in used_in_file:
                    if alpha not in self.used_alphas:
                        self.used_alphas[alpha] = []
                    self.used_alphas[alpha].append(f"indicator:{file_name}")

    def _extract_alpha_usage(self, py_file: Path) -> list[str]:
        """Extract alpha node function calls from a Python file."""
        used_alphas = []
        
        try:
            content = py_file.read_text()
            tree = ast.parse(content)
            
            # Track imports to understand what's being imported
            imported_functions = set()
            
            for node in ast.walk(tree):
                # Check for direct imports: from .module import function_node
                if isinstance(node, ast.ImportFrom):
                    if node.module and ("indicators" in str(node.module) or node.module in [".", ""]):
                        for alias in node.names or []:
                            if alias.name.endswith("_node"):
                                imported_functions.add(alias.name)
                
                # Check for function calls
                elif isinstance(node, ast.Call):
                    func_name = None
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr
                    
                    if func_name and func_name.endswith("_node"):
                        alpha_name = func_name.replace("_node", "")
                        if alpha_name in self.alpha_node_files:
                            used_alphas.append(alpha_name)
            
            # Also add imported functions
            for func_name in imported_functions:
                alpha_name = func_name.replace("_node", "")
                if alpha_name in self.alpha_node_files:
                    used_alphas.append(alpha_name)
                    
        except Exception:
            # Skip files that can't be parsed
            pass
            
        return list(set(used_alphas))  # Remove duplicates

    def generate_usage_report(self) -> dict[str, Any]:
        """Generate comprehensive usage report."""
        report = {
            "summary": {
                "total_implemented": len(self.implemented_alphas),
                "total_available_nodes": len(self.alpha_node_files),
                "total_used": len(self.used_alphas),
                "unused_count": len(self.alpha_node_files) - len(self.used_alphas)
            },
            "implemented_alphas": self.implemented_alphas,
            "usage": {
                "used_alphas": self.used_alphas,
                "unused_alphas": self._find_unused_alphas(),
                "unregistered_but_used": self._find_unregistered_used()
            },
            "files": {
                "alpha_node_files": self.alpha_node_files
            }
        }
        return report

    def _find_unused_alphas(self) -> list[str]:
        """Find alpha nodes that exist but are not used in any strategy."""
        return [
            alpha for alpha in self.alpha_node_files.keys()
            if alpha not in self.used_alphas
        ]

    def _find_unregistered_used(self) -> list[str]:
        """Find alphas that are used but not in the implemented registry."""
        registered_alpha_names = set()
        for alpha_info in self.implemented_alphas.values():
            for module in alpha_info["modules"]:
                if module.startswith("strategies/nodes/indicators/"):
                    # Extract alpha name from module path
                    module_name = Path(module).stem
                    registered_alpha_names.add(module_name)
        
        return [
            alpha for alpha in self.used_alphas.keys()
            if alpha not in registered_alpha_names
        ]

    def update_registry_with_usage(self, registry_path: Path = None) -> None:
        """Update the alphadocs registry with usage information."""
        if registry_path is None:
            registry_path = REGISTRY
            
        if not registry_path.exists():
            return
            
        data = yaml.safe_load(registry_path.read_text())
        
        # Create usage lookup by module path
        usage_by_module = {}
        for alpha, strategies in self.used_alphas.items():
            alpha_file = self.alpha_node_files.get(alpha)
            if alpha_file:
                usage_by_module[alpha_file] = {
                    "used": True,
                    "strategies": strategies
                }
        
        # Update registry entries
        for entry in data or []:
            if entry.get("status") == "implemented":
                modules = entry.get("modules", [])
                alpha_modules = [
                    m for m in modules 
                    if m.startswith("strategies/nodes/indicators/")
                ]
                
                # Check if any of this alpha's modules are used
                is_used = False
                used_in_strategies = []
                for module in alpha_modules:
                    if module in usage_by_module:
                        is_used = True
                        used_in_strategies.extend(usage_by_module[module]["strategies"])
                
                # Update entry with usage information
                entry["usage_status"] = "used" if is_used else "unused"
                if is_used:
                    entry["used_in_strategies"] = list(set(used_in_strategies))
        
        # Write back to registry
        registry_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    def format_table_report(self) -> str:
        """Format usage report as a readable table."""
        report = self.generate_usage_report()
        summary = report["summary"]
        
        lines = [
            "Alpha Usage Tracking Report",
            "=" * 50,
            f"Total Implemented Alphas: {summary['total_implemented']}",
            f"Total Available Alpha Nodes: {summary['total_available_nodes']}",
            f"Total Used Alpha Nodes: {summary['total_used']}",
            f"Unused Alpha Nodes: {summary['unused_count']}",
            "",
            "USED ALPHAS",
            "-" * 20
        ]
        
        for alpha, strategies in report["usage"]["used_alphas"].items():
            lines.append(f"{alpha:30} -> {', '.join(strategies)}")
        
        if report["usage"]["unused_alphas"]:
            lines.extend([
                "",
                "UNUSED ALPHAS",
                "-" * 20
            ])
            for alpha in report["usage"]["unused_alphas"]:
                file_path = self.alpha_node_files.get(alpha, "unknown")
                lines.append(f"{alpha:30} ({file_path})")
        
        if report["usage"]["unregistered_but_used"]:
            lines.extend([
                "",
                "UNREGISTERED BUT USED",
                "-" * 30
            ])
            for alpha in report["usage"]["unregistered_but_used"]:
                lines.append(f"{alpha:30} (not in registry)")
        
        return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Track alpha usage in strategies")
    parser.add_argument(
        "--format", 
        choices=["table", "json"], 
        default="table",
        help="Output format"
    )
    parser.add_argument(
        "--output",
        help="Output file (default: stdout)"
    )
    parser.add_argument(
        "--update-registry",
        action="store_true",
        help="Update alphadocs registry with usage information"
    )
    
    args = parser.parse_args()
    
    tracker = AlphaUsageTracker()
    tracker.load_implemented_alphas()
    tracker.scan_alpha_node_files()
    tracker.scan_strategy_usage()
    
    if args.update_registry:
        tracker.update_registry_with_usage()
        print("Registry updated with usage information")
    
    if args.format == "json":
        output = json.dumps(tracker.generate_usage_report(), indent=2)
    else:
        output = tracker.format_table_report()
    
    if args.output:
        Path(args.output).write_text(output)
        print(f"Report written to {args.output}")
    else:
        print(output)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())