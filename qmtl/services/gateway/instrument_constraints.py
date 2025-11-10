from __future__ import annotations

"""Venue and symbol normalization plus trading constraint resolution."""

from dataclasses import dataclass
from typing import Iterable, Mapping, MutableMapping


__all__ = [
    "ConstraintRule",
    "InstrumentConstraint",
    "ResolvedInstrument",
    "ConstraintViolation",
    "ConstraintViolationError",
    "InstrumentConstraints",
]


@dataclass(frozen=True)
class ConstraintRule:
    """Configuration rule describing venue/symbol level constraints."""

    venue: str | None = None
    symbol: str | None = None
    canonical_symbol: str | None = None
    lot_size: float | None = None
    min_notional: float | None = None
    tick_size: float | None = None
    aliases: Iterable[str] | None = None


@dataclass(frozen=True)
class InstrumentConstraint:
    """Concrete trading limits for a normalized instrument."""

    lot_size: float | None = None
    min_notional: float | None = None
    tick_size: float | None = None

    def merge(self, override: "InstrumentConstraint") -> "InstrumentConstraint":
        """Return a new constraint with ``override`` applied on top of ``self``."""

        return InstrumentConstraint(
            lot_size=override.lot_size if override.lot_size is not None else self.lot_size,
            min_notional=
                override.min_notional
                if override.min_notional is not None
                else self.min_notional,
            tick_size=override.tick_size if override.tick_size is not None else self.tick_size,
        )


@dataclass(frozen=True)
class ResolvedInstrument:
    """Result of resolving constraints for an input venue/symbol."""

    venue: str | None
    input_symbol: str
    symbol: str
    constraint: InstrumentConstraint


@dataclass(frozen=True)
class ConstraintViolation:
    """Captured when an order cannot satisfy the configured constraints."""

    venue: str | None
    symbol: str
    reason: str
    details: Mapping[str, object] | None = None


class ConstraintViolationError(RuntimeError):
    """Raised when constraint violations are configured to be fatal."""

    def __init__(self, violation: ConstraintViolation) -> None:
        self.violation = violation
        super().__init__(
            f"Constraint violation for {violation.symbol} on {violation.venue or 'default'}: {violation.reason}"
        )


class InstrumentConstraints:
    """Resolve venue/symbol pairs to canonical identifiers and limits."""

    def __init__(self, rules: Iterable[ConstraintRule] | None = None) -> None:
        self._rules: MutableMapping[tuple[str, str], tuple[str | None, InstrumentConstraint]] = {}
        self._aliases: MutableMapping[tuple[str, str], str] = {}
        if rules:
            for rule in rules:
                self.add_rule(rule)

    @staticmethod
    def _normalize_venue(value: str | None) -> str:
        if value is None:
            return ""
        if value == "*":
            return "*"
        return value.lower()

    @staticmethod
    def _normalize_symbol(value: str | None) -> str:
        if value is None or value == "*":
            return "*"
        return value.casefold()

    def add_rule(self, rule: ConstraintRule) -> None:
        """Register an additional constraint rule."""

        venue_key = self._normalize_venue(rule.venue)
        symbol_key = self._normalize_symbol(rule.symbol)
        canonical = rule.canonical_symbol or (rule.symbol if rule.symbol not in (None, "*") else None)
        constraint = InstrumentConstraint(
            lot_size=rule.lot_size,
            min_notional=rule.min_notional,
            tick_size=rule.tick_size,
        )
        self._rules[(venue_key, symbol_key)] = (canonical, constraint)

        # Register aliases for quick resolution.
        if rule.aliases:
            for alias in rule.aliases:
                alias_key = self._normalize_symbol(alias)
                self._aliases[(venue_key, alias_key)] = canonical or alias
        if canonical and rule.symbol not in (None, "*"):
            self._aliases.setdefault((venue_key, self._normalize_symbol(rule.symbol)), canonical)
        if canonical:
            self._aliases.setdefault(("*", self._normalize_symbol(canonical)), canonical)

    def resolve(self, venue: str | None, symbol: str) -> ResolvedInstrument:
        """Return the canonical symbol and merged constraints for ``(venue, symbol)``."""

        venue_key = self._normalize_venue(venue)
        symbol_key = self._normalize_symbol(symbol)
        canonical = self._resolve_symbol_alias(venue_key, symbol_key) or symbol
        lookup_key = self._normalize_symbol(canonical)

        constraint = InstrumentConstraint()
        canonical_override: str | None = None
        for candidate in (
            ("*", "*"),
            ("*", lookup_key),
            ("", "*"),
            ("", lookup_key),
            (venue_key, "*"),
            (venue_key, lookup_key),
        ):
            rule = self._rules.get(candidate)
            if not rule:
                continue
            rule_canonical, rule_constraint = rule
            constraint = constraint.merge(rule_constraint)
            if rule_canonical:
                canonical_override = rule_canonical

        resolved_symbol = canonical_override or canonical
        return ResolvedInstrument(
            venue=venue,
            input_symbol=symbol,
            symbol=resolved_symbol,
            constraint=constraint,
        )

    def _resolve_symbol_alias(self, venue_key: str, symbol_key: str) -> str | None:
        for candidate in ((venue_key, symbol_key), ("", symbol_key), ("*", symbol_key)):
            alias = self._aliases.get(candidate)
            if alias is not None:
                return alias
        return None
