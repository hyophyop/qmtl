#!/usr/bin/env python3
"""Helper script to list unused alpha implementations."""

from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.track_alpha_usage import AlphaUsageTracker


def main() -> int:
    """Show only unused alphas for quick identification."""
    tracker = AlphaUsageTracker()
    tracker.load_implemented_alphas()
    tracker.scan_alpha_node_files()
    tracker.scan_strategy_usage()
    
    report = tracker.generate_usage_report()
    unused = report["usage"]["unused_alphas"]
    
    if not unused:
        print("✅ All alpha implementations are being used!")
        return 0
    
    print(f"⚠️  Found {len(unused)} unused alpha implementations:")
    print()
    
    for alpha in unused:
        file_path = tracker.alpha_node_files.get(alpha, "unknown location")
        print(f"  • {alpha}")
        print(f"    Location: {file_path}")
        
        # Find corresponding registry entry if it exists
        for alpha_name, info in tracker.implemented_alphas.items():
            if any(file_path in module for module in info["modules"]):
                print(f"    Documentation: {info['doc']}")
                break
        print()
    
    print(f"Consider reviewing these {len(unused)} alpha implementations.")
    print("They may be ready for integration into strategy DAGs or could be deprecated.")
    
    return len(unused)  # Return count as exit code for scripting


if __name__ == "__main__":
    raise SystemExit(main())