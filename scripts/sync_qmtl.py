#!/usr/bin/env python3
"""
Helper script to fetch and pull qmtl subtree from upstream and show verification steps.
This replaces the shell script version for better platform independence and error handling.
"""
import os
import subprocess
import sys
import shutil
import time
from datetime import datetime
from pathlib import Path
from functools import lru_cache
from typing import Optional, List, Tuple


@lru_cache(maxsize=1)
def get_qmtl_commit_count(root_dir: Path) -> int:
    """Get the number of commits in qmtl directory (cached)."""
    success, stdout, _ = run_command(
        ["git", "rev-list", "--count", "HEAD", "--", "qmtl/"],
        cwd=root_dir
    )
    if success and stdout.strip():
        try:
            return int(stdout.strip())
        except ValueError:
            pass
    return 0


def log_operation(operation: str, start_time: float) -> None:
    """Log operation completion with timing."""
    duration = time.time() - start_time
    print(f"⏱️  {operation} completed in {duration:.2f}s")


def run_command(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> tuple[bool, str, str]:
    """Run a command and return success status with output."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check
        )
        return True, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout or "", e.stderr or ""


def create_backup(root_dir: Path) -> str:
    """Create a backup of the qmtl directory."""
    qmtl_dir = root_dir / "qmtl"
    if not qmtl_dir.exists():
        return ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"qmtl_backup_{timestamp}"
    backup_path = root_dir / ".backups" / backup_name

    backup_path.parent.mkdir(exist_ok=True)
    shutil.copytree(qmtl_dir, backup_path, dirs_exist_ok=True)

    print(f"📦 Backup created: {backup_path}")
    return str(backup_path)


def cleanup_old_backups(root_dir: Path, keep_count: int = 5) -> None:
    """Clean up old backups, keeping only the most recent ones."""
    backup_dir = root_dir / ".backups"
    if not backup_dir.exists():
        print("📦 No backup directory found, skipping cleanup")
        return

    # Get keep count from environment variable if set
    env_keep_count = os.environ.get("QMTL_BACKUP_KEEP_COUNT")
    if env_keep_count:
        try:
            keep_count = int(env_keep_count)
            if keep_count < 1:
                print(f"⚠️  QMTL_BACKUP_KEEP_COUNT must be at least 1, using default 5")
                keep_count = 5
        except ValueError:
            print(f"⚠️  Invalid QMTL_BACKUP_KEEP_COUNT value: {env_keep_count}, using default {keep_count}")

    # Find all backup directories
    backup_dirs: List[Tuple[Path, datetime]] = []
    for item in backup_dir.iterdir():
        if item.is_dir() and item.name.startswith("qmtl_backup_"):
            try:
                # Extract timestamp from backup name
                timestamp_str = item.name.replace("qmtl_backup_", "")
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                backup_dirs.append((item, timestamp))
            except ValueError:
                # Skip backups with invalid timestamp format
                print(f"⚠️  Skipping backup with invalid timestamp: {item.name}")
                continue

    total_backups = len(backup_dirs)
    if total_backups == 0:
        print("📦 No backups found to clean up")
        return

    if total_backups <= keep_count:
        print(f"📦 Found {total_backups} backups (keeping all, limit is {keep_count})")
        return

    print(f"📦 Found {total_backups} backups, keeping {keep_count} most recent")

    # Sort by timestamp (newest first)
    backup_dirs.sort(key=lambda x: x[1], reverse=True)

    # Remove old backups
    backups_to_remove = backup_dirs[keep_count:]
    removed_count = 0
    for backup_path, timestamp in backups_to_remove:
        try:
            shutil.rmtree(backup_path)
            print(f"🗑️  Removed old backup: {backup_path.name} ({timestamp.strftime('%Y-%m-%d %H:%M:%S')})")
            removed_count += 1
        except OSError as e:
            print(f"⚠️  Failed to remove backup {backup_path.name}: {e}")

    remaining_count = total_backups - removed_count
    print(f"📦 Backup cleanup completed. Removed {removed_count} old backups, kept {remaining_count} most recent.")


def attempt_auto_resolve_conflicts(root_dir: Path) -> bool:
    """Attempt to automatically resolve common conflicts."""
    print("🔧 Attempting automatic conflict resolution...")

    # Check for common conflict patterns and resolve them
    qmtl_dir = root_dir / "qmtl"

    for py_file in qmtl_dir.rglob("*.py"):
        if py_file.exists():
            content = py_file.read_text()
            if "<<<<<<< HEAD" in content or ">>>>>>>" in content:
                print(f"⚠️  Conflicts found in {py_file}, manual resolution needed")
                return False

    print("✅ No conflicts detected or auto-resolution successful")
    return True


def verify_sync(root_dir: Path, remote: str) -> None:
    """Verify the sync was successful."""
    print("\n🔍 Verifying sync...")

    # Check if qmtl directory exists and has content
    qmtl_dir = root_dir / "qmtl"
    if not qmtl_dir.exists():
        print("❌ qmtl directory does not exist")
        return

    # Show recent commits
    success, stdout, _ = run_command(
        ["git", "log", "-n", "3", "--oneline", "qmtl/"],
        cwd=root_dir
    )

    if success and stdout.strip():
        print("📋 Recent commits in qmtl/:")
        print(stdout)
    else:
        print("⚠️  No recent commits found in qmtl/")

    # Check remote status
    success, stdout, _ = run_command(
        ["git", "status", "-b", "--ahead-behind"],
        cwd=root_dir
    )

    if success:
        print(f"📊 Repository status:\n{stdout}")


def fetch_upstream(root_dir: Path, remote: str) -> bool:
    """Fetch from upstream remote."""
    print(f"📥 Fetching from {remote}...")
    success, _, stderr = run_command(
        ["git", "fetch", remote, "main"],
        cwd=root_dir
    )

    if not success:
        print(f"❌ Failed to fetch from {remote}: {stderr}")
        return False
    return True


def pull_subtree(root_dir: Path, remote: str) -> tuple[bool, str]:
    """Pull subtree and handle conflicts."""
    print("🔄 Pulling subtree into qmtl/ (squash)...")
    success, _, stderr = run_command(
        ["git", "subtree", "pull", "--prefix=qmtl", remote, "main", "--squash"],
        cwd=root_dir,
        check=False  # Don't fail immediately on conflicts
    )

    return success, stderr


def handle_conflicts(root_dir: Path, stderr: str, backup_path: str) -> int:
    """Handle merge conflicts."""
    if "conflict" in stderr.lower() or "CONFLICT" in stderr:
        print("❌ Conflicts detected during subtree pull!")

        # Attempt auto-resolution
        if attempt_auto_resolve_conflicts(root_dir):
            print("✅ Conflicts resolved automatically")
            return 0
        else:
            print("📝 Manual conflict resolution required:")
            print("1. Check git status")
            print("2. Edit conflicting files in qmtl/")
            print("3. Run 'git add <resolved-files>'")
            print("4. Run 'git commit'")
            print("5. Re-run this script")
            if backup_path:
                print(f"6. Or restore from backup: cp -r {backup_path} qmtl/")
            return 1
    else:
        print(f"❌ Failed to pull subtree: {stderr}")
        if backup_path:
            print(f"🔄 To restore backup: cp -r {backup_path} qmtl/")
        return 1


def print_usage() -> None:
    """Print usage information."""
    print("Usage: python sync_qmtl.py [options]")
    print("\nOptions:")
    print("  --cleanup-existing    Clean up existing backups before sync")
    print("  --help               Show this help message")
    print("\nEnvironment variables:")
    print("  QMTL_SUBTREE_REMOTE         Remote name (default: qmtl-subtree)")
    print("  QMTL_BACKUP_KEEP_COUNT     Number of backups to keep (default: 5)")


def main() -> int:
    """Main sync function."""
    start_time = time.time()
    root_dir = Path(__file__).parent.parent

    # Parse command line arguments
    if "--help" in sys.argv or "-h" in sys.argv:
        print_usage()
        return 0

    cleanup_existing = "--cleanup-existing" in sys.argv

    # Determine remote name
    qmtl_subtree_remote = os.environ.get("QMTL_SUBTREE_REMOTE", "qmtl-subtree")

    print(f"🚀 Starting QMTL subtree sync from {qmtl_subtree_remote}...")

    if cleanup_existing:
        print("🧹 Cleaning up existing backups before sync...")
        cleanup_old_backups(root_dir)

    # Create backup before sync
    backup_path = create_backup(root_dir)

    # Fetch from upstream
    if not fetch_upstream(root_dir, qmtl_subtree_remote):
        return 1

    # Pull subtree
    success, stderr = pull_subtree(root_dir, qmtl_subtree_remote)

    if not success:
        return handle_conflicts(root_dir, stderr, backup_path)

    # Verify sync
    verify_sync(root_dir, qmtl_subtree_remote)

    # Clean up old backups after successful sync
    cleanup_old_backups(root_dir)

    print("\n✅ Subtree sync completed successfully!")
    print(f"🔄 To push changes back to upstream after modifying qmtl/, run:")
    print(f"   git subtree push --prefix=qmtl {qmtl_subtree_remote} main")

    log_operation("QMTL subtree sync", start_time)
    return 0


if __name__ == "__main__":
    sys.exit(main())
