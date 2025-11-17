"""Shared-account execution policy helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, cast


def _lookup_mark(
    marks: Mapping[tuple[str | None, str], float],
    symbol: str,
    venue: str | None,
) -> float | None:
    """Return a representative mark for ``symbol`` on ``venue`` if available."""

    candidates: list[tuple[str | None, str]] = []
    if venue:
        candidates.append((venue, symbol))
        venue_lower = venue.lower()
        if venue_lower != venue:
            candidates.append((venue_lower, symbol))
    candidates.append((None, symbol))
    for key in candidates:
        mark = marks.get(key)
        if mark is not None and mark > 0:
            return float(mark)
    return None


@dataclass(frozen=True)
class SharedAccountPolicyConfig:
    """Configuration controlling shared-account execution guards."""

    enabled: bool = False
    max_gross_notional: float | None = None
    max_net_notional: float | None = None
    min_margin_headroom: float | None = None

    def as_policy(self) -> "SharedAccountPolicy":
        """Build a :class:`SharedAccountPolicy` for runtime enforcement."""

        return SharedAccountPolicy(config=self)


@dataclass(frozen=True)
class SharedAccountPolicyResult:
    """Outcome from evaluating a shared-account execution request."""

    allowed: bool
    reason: str | None = None
    context: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SharedAccountPolicy:
    """Evaluate risk constraints before allowing shared-account execution."""

    config: SharedAccountPolicyConfig

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    def evaluate(
        self,
        orders: Sequence[Mapping[str, object]],
        *,
        marks_by_symbol: Mapping[tuple[str | None, str], float],
        total_equity: float,
        current_net_notional: float | None = None,
    ) -> SharedAccountPolicyResult:
        """Return whether ``orders`` satisfy configured constraints."""

        current_net = float(current_net_notional or 0.0)
        metrics = self._baseline_metrics(total_equity, current_net)

        gross, net, missing_marks = self._accumulate_notional(
            orders, marks_by_symbol
        )
        projected_net, projected_net_abs = self._project_net(current_net, net)
        margin_headroom = self._margin_headroom(total_equity, projected_net_abs)

        metrics.update(
            {
                "gross_notional": gross,
                "net_notional_delta": abs(net),
                "net_notional": projected_net_abs,
                "margin_headroom": margin_headroom,
            }
        )

        if missing_marks:
            metrics["missing_marks"] = missing_marks
            return SharedAccountPolicyResult(
                allowed=False,
                reason="missing mark data for shared-account exposure evaluation",
                context=metrics,
            )

        return self._enforce_limits(
            metrics,
            gross,
            projected_net_abs,
            margin_headroom,
            total_equity,
        )

    def _baseline_metrics(self, total_equity: float, current_net: float) -> dict[str, object]:
        metrics: dict[str, object] = {"total_equity": float(total_equity)}
        if current_net:
            metrics["current_net_notional"] = abs(current_net)
        return metrics

    def _accumulate_notional(
        self,
        orders: Sequence[Mapping[str, object]],
        marks_by_symbol: Mapping[tuple[str | None, str], float],
    ) -> tuple[float, float, list[Mapping[str, str | None]]]:
        gross = 0.0
        net = 0.0
        missing_marks: list[Mapping[str, str | None]] = []

        for order in orders:
            qty_raw = order.get("quantity", 0.0)
            qty = self._safe_float(qty_raw)
            if qty is None or qty == 0.0:
                continue
            symbol = str(order.get("symbol", "") or "")
            venue = order.get("venue")
            mark = _lookup_mark(
                marks_by_symbol, symbol, str(venue) if venue else None
            )
            if mark is None:
                missing_marks.append(
                    {"symbol": symbol or None, "venue": venue if isinstance(venue, str) else None}
                )
                continue
            notional = abs(qty) * mark
            gross += notional
            net += qty * mark

        return gross, net, missing_marks

    def _project_net(self, current_net: float, net_delta: float) -> tuple[float, float]:
        projected = current_net + net_delta
        return projected, abs(projected)

    def _margin_headroom(self, total_equity: float, projected_net_abs: float) -> float:
        if total_equity <= 0:
            return 0.0
        return max(0.0, 1.0 - (projected_net_abs / total_equity))

    def _enforce_limits(
        self,
        metrics: Mapping[str, object],
        gross: float,
        projected_net_abs: float,
        margin_headroom: float,
        total_equity: float,
    ) -> SharedAccountPolicyResult:
        cfg = self.config
        eps = 1e-9

        if cfg.max_gross_notional is not None and gross - cfg.max_gross_notional > eps:
            return SharedAccountPolicyResult(
                allowed=False,
                reason=(
                    f"gross notional {gross:.2f} exceeds limit {cfg.max_gross_notional:.2f}"
                ),
                context=metrics,
            )

        if (
            cfg.max_net_notional is not None
            and projected_net_abs - cfg.max_net_notional > eps
        ):
            return SharedAccountPolicyResult(
                allowed=False,
                reason=(
                    f"net notional {projected_net_abs:.2f} exceeds limit {cfg.max_net_notional:.2f}"
                ),
                context=metrics,
            )

        if cfg.min_margin_headroom is not None:
            if total_equity <= 0:
                return SharedAccountPolicyResult(
                    allowed=False,
                    reason="margin headroom check requires positive total_equity",
                    context=metrics,
                )
            if margin_headroom + eps < cfg.min_margin_headroom:
                return SharedAccountPolicyResult(
                    allowed=False,
                    reason=(
                        f"margin headroom {margin_headroom:.4f} below minimum {cfg.min_margin_headroom:.4f}"
                    ),
                    context=metrics,
                )

        return SharedAccountPolicyResult(allowed=True, context=metrics)

    def _safe_float(self, value: object) -> float | None:
        try:
            return float(cast(Any, value))
        except Exception:
            return None


__all__ = [
    "SharedAccountPolicy",
    "SharedAccountPolicyConfig",
    "SharedAccountPolicyResult",
]
