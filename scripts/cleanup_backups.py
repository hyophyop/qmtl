#!/usr/bin/env python3
"""
Backup cleanup utility for QMTL strategies.
This script helps manage existing backups that were created before the automatic cleanup feature.
"""
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


def cleanup_old_backups(root_dir: Path, keep_count: int = 5, dry_run: bool = False) -> None:
    """Clean up old backups, keeping only the most recent ones."""
    backup_dir = root_dir / ".backups"
    if not backup_dir.exists():
        print("📦 No backup directory found")
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
    backup_dirs: List[Tuple[Path, datetime, float]] = []
    for item in backup_dir.iterdir():
        if item.is_dir() and item.name.startswith("qmtl_backup_"):
            try:
                # Extract timestamp from backup name
                timestamp_str = item.name.replace("qmtl_backup_", "")
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                size_mb = get_directory_size_mb(item)
                backup_dirs.append((item, timestamp, size_mb))
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
    if dry_run:
        print("🔍 DRY RUN MODE - No files will be deleted")

    # Sort by timestamp (newest first)
    backup_dirs.sort(key=lambda x: x[1], reverse=True)

    # Show what would be removed
    backups_to_remove = backup_dirs[keep_count:]
    print(f"\n📋 Backups to {'remove' if not dry_run else 'be removed (dry run)'}:")

    for backup_path, timestamp, size_mb in backups_to_remove:
        print(f"  🗑️  {backup_path.name} ({timestamp.strftime('%Y-%m-%d %H:%M:%S')}) - {size_mb:.1f} MB")

    if dry_run:
        print(f"\n📦 Would remove {len(backups_to_remove)} old backups, keep {keep_count} most recent.")
        return

    # Confirm before removing
    if not confirm_action(f"Remove {len(backups_to_remove)} old backups?"):
        print("❌ Cleanup cancelled by user")
        return

    # Remove old backups
    removed_count = 0
    total_size_mb = 0
    for backup_path, timestamp, size_mb in backups_to_remove:
        try:
            shutil.rmtree(backup_path)
            print(f"🗑️  Removed old backup: {backup_path.name} ({timestamp.strftime('%Y-%m-%d %H:%M:%S')}) - {size_mb:.1f} MB")
            removed_count += 1
            total_size_mb += size_mb
        except OSError as e:
            print(f"⚠️  Failed to remove backup {backup_path.name}: {e}")

    remaining_count = total_backups - removed_count
    print(f"\n📦 Backup cleanup completed!")
    print(f"  • Removed: {removed_count} old backups")
    print(f"  • Space freed: {total_size_mb:.1f} MB")
    print(f"  • Kept: {remaining_count} most recent backups")


def get_directory_size_mb(path: Path) -> float:
    """Get directory size in MB."""
    total_size = 0
    for file_path in path.rglob('*'):
        if file_path.is_file():
            total_size += file_path.stat().st_size
    return total_size / (1024 * 1024)


def confirm_action(message: str) -> bool:
    """Get user confirmation for destructive actions."""
    try:
        response = input(f"⚠️  {message} (y/N): ").strip().lower()
        return response in ['y', 'yes']
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
        return False


def show_backup_stats(root_dir: Path) -> None:
    """Show statistics about existing backups."""
    backup_dir = root_dir / ".backups"
    if not backup_dir.exists():
        print("📦 No backup directory found")
        return

    backup_dirs: List[Tuple[Path, datetime, float]] = []
    total_size_mb = 0

    for item in backup_dir.iterdir():
        if item.is_dir() and item.name.startswith("qmtl_backup_"):
            try:
                timestamp_str = item.name.replace("qmtl_backup_", "")
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                size_mb = get_directory_size_mb(item)
                backup_dirs.append((item, timestamp, size_mb))
                total_size_mb += size_mb
            except ValueError:
                continue

    if not backup_dirs:
        print("📦 No valid backups found")
        return

    # Sort by timestamp (newest first)
    backup_dirs.sort(key=lambda x: x[1], reverse=True)

    print(f"📊 Backup Statistics:")
    print(f"  • Total backups: {len(backup_dirs)}")
    print(f"  • Total size: {total_size_mb:.1f} MB")
    print(f"  • Average size: {total_size_mb/len(backup_dirs):.1f} MB per backup")
    print(f"  • Newest: {backup_dirs[0][0].name} ({backup_dirs[0][1].strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"  • Oldest: {backup_dirs[-1][0].name} ({backup_dirs[-1][1].strftime('%Y-%m-%d %H:%M:%S')})")


def main() -> int:
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python cleanup_backups.py <command> [options]")
        print("\nCommands:")
        print("  cleanup    Clean up old backups")
        print("  stats      Show backup statistics")
        print("  dry-run    Show what would be cleaned up without deleting")
        print("\nEnvironment variables:")
        print("  QMTL_BACKUP_KEEP_COUNT    Number of backups to keep (default: 5)")
        return 1

    root_dir = Path(__file__).parent.parent
    command = sys.argv[1].lower()

    if command == "stats":
        show_backup_stats(root_dir)
    elif command == "dry-run":
        cleanup_old_backups(root_dir, dry_run=True)
    elif command == "cleanup":
        cleanup_old_backups(root_dir)
    else:
        print(f"❌ Unknown command: {command}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
