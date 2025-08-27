"""
Scripts package for QMTL Strategies project automation.
Provides common utilities for project maintenance tasks.
"""
import subprocess
import sys
from pathlib import Path
from typing import Optional


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def run_command(
    cmd: list[str],
    cwd: Optional[Path] = None,
    check: bool = True,
    capture_output: bool = True
) -> tuple[bool, str, str]:
    """
    Run a command and return success status with output.

    Args:
        cmd: Command to run as list of strings
        cwd: Working directory for the command
        check: Whether to raise exception on failure
        capture_output: Whether to capture stdout/stderr

    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        if capture_output:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=check
            )
            return True, result.stdout or "", result.stderr or ""
        else:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                check=check
            )
            return True, "", ""

    except subprocess.CalledProcessError as e:
        if capture_output:
            return False, e.stdout or "", e.stderr or ""
        else:
            return False, "", str(e)


def ensure_uv_installed() -> bool:
    """Ensure uv package manager is installed."""
    success, _, stderr = run_command([sys.executable, "-m", "pip", "install", "uv"])
    if not success:
        print(f"Failed to install uv: {stderr}")
        return False
    return True


def ensure_venv_exists() -> bool:
    """Ensure virtual environment exists."""
    root_dir = get_project_root()
    venv_path = root_dir / ".venv"

    if not venv_path.exists():
        print("Creating virtual environment...")
        success, _, stderr = run_command(["uv", "venv"], cwd=root_dir)
        if not success:
            print(f"Failed to create venv: {stderr}")
            return False

    return True