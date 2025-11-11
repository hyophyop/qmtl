"""Shared-account execution policy helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


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

        metrics: dict[str, object] = {
            "total_equity": float(total_equity),
        }

        gross = 0.0
        net = 0.0
        missing_marks: list[Mapping[str, str | None]] = []
        current_net = float(current_net_notional or 0.0)
        if current_net:
            metrics["current_net_notional"] = abs(current_net)

        for order in orders:
            qty_raw = order.get("quantity", 0.0)
            try:
                qty = float(qty_raw)
            except Exception:
                continue
            if qty == 0.0:
                continue
            symbol = str(order.get("symbol", "") or "")
            venue = order.get("venue")
            mark = _lookup_mark(marks_by_symbol, symbol, str(venue) if venue else None)
            if mark is None:
                missing_marks.append({"symbol": symbol or None, "venue": venue if isinstance(venue, str) else None})
                continue
            notional = abs(qty) * mark
            gross += notional
            net += qty * mark

        net_abs = abs(net)
        projected_net = current_net + net
        projected_net_abs = abs(projected_net)
        metrics["gross_notional"] = gross
        metrics["net_notional_delta"] = net_abs
        metrics["net_notional"] = projected_net_abs
        if missing_marks:
            metrics["missing_marks"] = missing_marks

        margin_headroom = 0.0
        if total_equity > 0:
            margin_headroom = max(0.0, 1.0 - (projected_net_abs / total_equity))
        metrics["margin_headroom"] = margin_headroom

        if missing_marks:
            return SharedAccountPolicyResult(
                allowed=False,
                reason="missing mark data for shared-account exposure evaluation",
                context=metrics,
            )

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

        if cfg.max_net_notional is not None and projected_net_abs - cfg.max_net_notional > eps:
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


__all__ = [
    "SharedAccountPolicy",
    "SharedAccountPolicyConfig",
    "SharedAccountPolicyResult",
]
