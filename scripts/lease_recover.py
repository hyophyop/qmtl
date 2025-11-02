"""Manual recovery tooling for the Seamless backfill coordinator.

The distributed coordinator protects backfill work through short-lived
leases. When a worker crashes or loses connectivity the lease may remain
allocated until it expires. Operators can use this script to explicitly
release those leases so other workers can resume processing immediately.

The script accepts ``KEY:TOKEN`` pairs on the command line or via a file
of newline-delimited entries. Tokens are required so the coordinator can
validate that the caller is taking over the correct lease; obtain them
from the coordinator's ``/v1/leases/inspect`` endpoint or directly from
logs emitted by stuck workers.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from qmtl.runtime.sdk.backfill_coordinator import (
    DistributedBackfillCoordinator,
    Lease,
)
from qmtl.runtime.sdk.configuration import get_seamless_config


@dataclass(frozen=True)
class LeaseSpec:
    """Normalized representation of a lease identifier."""

    key: str
    token: str | None = None

    @classmethod
    def parse(cls, raw: str) -> "LeaseSpec":
        if not raw:
            raise ValueError("Empty lease spec")
        parts = raw.split(":", 1)
        if len(parts) == 1:
            return cls(key=parts[0].strip() or raw.strip(), token=None)
        key, token = parts[0].strip(), parts[1].strip()
        if not key:
            raise ValueError(f"Invalid lease spec '{raw}': missing key")
        return cls(key=key, token=token or None)


@dataclass(frozen=True)
class LeaseRecoverySummary:
    processed: int
    released: int
    skipped: int
    errors: tuple[str, ...]


async def recover_leases(
    lease_specs: Sequence[LeaseSpec],
    *,
    coordinator: DistributedBackfillCoordinator | None = None,
    base_url: str | None = None,
    action: str = "fail",
    reason: str = "manual_recovery",
    dry_run: bool = False,
) -> LeaseRecoverySummary:
    """Release or complete leases via the distributed coordinator."""

    if coordinator is None:
        if not base_url:
            raise ValueError("Either 'coordinator' or 'base_url' must be provided")
        coordinator = DistributedBackfillCoordinator(base_url=base_url)

    processed = 0
    released = 0
    skipped = 0
    errors: list[str] = []

    for spec in lease_specs:
        processed += 1
        if dry_run:
            skipped += 1
            continue
        if spec.token is None:
            skipped += 1
            errors.append(f"missing token for lease '{spec.key}'")
            continue
        lease = Lease(key=spec.key, token=spec.token, lease_until_ms=0)
        try:
            if action == "complete":
                await coordinator.complete(lease)
            else:
                await coordinator.fail(lease, reason)
            released += 1
        except Exception as exc:  # pragma: no cover - network errors
            errors.append(f"{spec.key}: {exc}")

    return LeaseRecoverySummary(
        processed=processed,
        released=released,
        skipped=skipped,
        errors=tuple(errors),
    )


def _read_specs(values: Sequence[str], from_file: Path | None) -> list[LeaseSpec]:
    raw: list[str] = list(values)
    if from_file:
        raw.extend(line.strip() for line in from_file.read_text().splitlines())
    specs: list[LeaseSpec] = []
    for entry in raw:
        entry = entry.strip()
        if not entry:
            continue
        specs.append(LeaseSpec.parse(entry))
    return specs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "leases",
        nargs="*",
        help="Lease specs in KEY:TOKEN form. Tokens are required unless --dry-run is used.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        dest="config",
        help="Optional path to qmtl.yml. Defaults to auto-discovery when omitted.",
    )
    parser.add_argument(
        "--coordinator-url",
        dest="coordinator_url",
        default=None,
        help="Base URL for the distributed backfill coordinator (overrides configuration).",
    )
    parser.add_argument(
        "--from-file",
        type=Path,
        dest="from_file",
        help="Path to a file containing newline-delimited lease specs.",
    )
    parser.add_argument(
        "--action",
        choices={"fail", "complete"},
        default="fail",
        help="Whether to mark the lease as failed (default) or completed.",
    )
    parser.add_argument(
        "--reason",
        default="manual_recovery",
        help="Reason string submitted when failing leases.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse inputs but do not contact the coordinator.",
    )
    return parser


async def _run_async(args: argparse.Namespace) -> LeaseRecoverySummary:
    specs = _read_specs(args.leases, args.from_file)
    if not specs:
        raise SystemExit("No leases supplied")
    coordinator_url = args.coordinator_url
    coordinator = None
    if not coordinator_url:
        cfg = get_seamless_config(args.config)
        coordinator_url = (cfg.coordinator_url or "").strip()
    if coordinator_url:
        coordinator = DistributedBackfillCoordinator(base_url=coordinator_url)
    summary = await recover_leases(
        specs,
        coordinator=coordinator,
        base_url=None if coordinator is not None else coordinator_url,
        action=args.action,
        reason=args.reason,
        dry_run=args.dry_run,
    )
    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        summary = asyncio.run(_run_async(args))
    except ValueError as exc:
        parser.error(str(exc))
        return 2
    except SystemExit as exc:
        raise exc
    except Exception as exc:  # pragma: no cover - defensive
        parser.error(str(exc))
        return 2

    if summary.errors:
        for error in summary.errors:
            print(f"error: {error}", file=sys.stderr)
    print(
        f"processed={summary.processed} released={summary.released} skipped={summary.skipped}",
        file=sys.stdout,
    )
    return 0 if not summary.errors else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
