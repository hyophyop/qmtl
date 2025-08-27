#!/usr/bin/env python3
"""
Bootstrap script to create a uv venv, install editable qmtl dev deps and run a smoke test.
This replaces the shell script version for better platform independence.
"""
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], cwd: Path | None = None) -> bool:
    """Run a command and return success status."""
    try:
        subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(cmd)}")
        print(f"Error: {e.stderr}")
        return False


def main() -> int:
    """Main bootstrap function."""
    root_dir = Path(__file__).parent.parent
    print("Creating uv venv and installing development dependencies...")

    # Install/upgrade pip and uv
    run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run_command([sys.executable, "-m", "pip", "install", "uv"])

    # Create venv and install dependencies
    if not run_command(["uv", "venv"], cwd=root_dir):
        return 1

    if not run_command(["uv", "pip", "install", "-e", "qmtl[dev]"], cwd=root_dir):
        return 1

    if not run_command(["uv", "pip", "install", "pyyaml"], cwd=root_dir):
        return 1

    print("Running a quick smoke test (strategy tests)...")

    # Run smoke test
    test_cmd = ["uv", "run", "-m", "pytest", "-q", "--maxfail=1"]
    if (root_dir / "strategies" / "tests").exists():
        test_cmd.append("strategies/tests")

    if not run_command(test_cmd, cwd=root_dir):
        print("Warning: Smoke test failed, but bootstrap completed")
        return 1

    print("Bootstrap complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
