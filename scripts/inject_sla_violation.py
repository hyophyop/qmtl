"""Emit synthetic Seamless SLA metrics for alert validation.

Operators can use this helper to push controlled observations into the
Prometheus registry that backs Seamless dashboards. The generated samples
make it possible to verify alert rules, Grafana panels, and PagerDuty
wiring without waiting for a production incident.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Iterable, Sequence

from qmtl.runtime.sdk import metrics as sdk_metrics

_DEFAULT_PHASES: tuple[str, ...] = (
    "storage_wait",
    "backfill_wait",
    "live_wait",
    "total",
)


def inject_samples(
    *,
    node_id: str,
    phases: Sequence[str] = _DEFAULT_PHASES,
    duration_seconds: float = 180.0,
    repetitions: int = 10,
    output_path: Path | None = None,
) -> str:
    """Populate the SDK metrics registry with synthetic SLA samples."""

    sdk_metrics.reset_metrics()
    for _ in range(repetitions):
        for phase in phases:
            sdk_metrics.observe_sla_phase_duration(
                node_id=node_id,
                phase=phase,
                duration_seconds=duration_seconds,
            )
    rendered = sdk_metrics.collect_metrics()
    if output_path:
        output_path.write_text(rendered)
    return rendered


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("node_id", help="Node identifier used to label the synthetic samples.")
    parser.add_argument(
        "--duration",
        type=float,
        default=180.0,
        help="Duration (seconds) recorded for each observation. Default: 180 seconds.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=10,
        help="Number of samples to record for each phase. Default: 10 repetitions.",
    )
    parser.add_argument(
        "--phase",
        dest="phases",
        action="append",
        help="Specific phases to record. Can be specified multiple times. Defaults to all phases.",
    )
    parser.add_argument(
        "--write-to",
        type=Path,
        help="Optional path that will receive the rendered Prometheus exposition text.",
    )
    parser.add_argument(
        "--serve",
        type=int,
        metavar="PORT",
        help="If provided, expose the generated metrics over HTTP on the given port.",
    )
    parser.add_argument(
        "--hold",
        type=float,
        default=60.0,
        help="How long to keep the HTTP server alive when --serve is set. Default: 60 seconds.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    phases = tuple(args.phases) if args.phases else _DEFAULT_PHASES
    metrics_text = inject_samples(
        node_id=args.node_id,
        phases=phases,
        duration_seconds=args.duration,
        repetitions=args.repetitions,
        output_path=args.write_to,
    )

    if args.serve:
        sdk_metrics.start_metrics_server(port=args.serve)
        print(f"Serving metrics on 0.0.0.0:{args.serve} for {args.hold} seconds...")
        time.sleep(max(args.hold, 0.0))
    else:
        print(metrics_text)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
