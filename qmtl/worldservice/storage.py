from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .policy_engine import Policy


ALLOWED_DOMAINS = {"backtest", "dryrun", "live", "shadow"}


def _normalize_domain(name: str | None) -> str:
    if not name:
        raise ValueError("domain is required")
    value = name.lower()
    if value not in ALLOWED_DOMAINS:
        raise ValueError(f"unsupported domain: {name}")
    return value


def _effective_mode_for_domain(domain: str) -> str:
    mapping = {
        "backtest": "compute-only",
        "dryrun": "paper",
        "live": "live",
        "shadow": "validate",
    }
    return mapping.get(domain, "compute-only")


@dataclass
class WorldActivation:
    """Activation state for a world."""

    version: int = 0
    state: Dict[str, Dict[str, float | bool]] = field(default_factory=dict)


@dataclass
class WorldPolicies:
    """Policy versions for a world."""

    versions: Dict[int, Policy] = field(default_factory=dict)
    default: Optional[int] = None


@dataclass
class WorldAuditLog:
    """Audit entries for a world."""

    entries: List[Dict] = field(default_factory=list)


@dataclass
class DomainState:
    """Lifecycle state for a world's execution domain."""

    current: str = "backtest"
    previous: Optional[str] = None
    pending: Optional[str] = None
    run_id: Optional[str] = None
    phase: str = "steady"
    freeze: bool = False
    drain: bool = False
    last_transition_at: Optional[str] = None

    def snapshot(self) -> Dict[str, Optional[str] | bool]:
        return {
            "current": self.current,
            "previous": self.previous,
            "pending": self.pending,
            "run_id": self.run_id,
            "phase": self.phase,
            "freeze": self.freeze,
            "drain": self.drain,
            "last_transition_at": self.last_transition_at,
        }


@dataclass
class DomainTransition:
    """Transition intent supplied by callers of :meth:`apply_transition`."""

    run_id: str
    phase: str
    target: Optional[str] = None


class Storage:
    """In-memory storage backing WorldService endpoints.

    This lightweight layer mimics Redis/DB backed models for tests.
    """

    def __init__(self) -> None:
        self.worlds: Dict[str, Dict] = {}
        self.activations: Dict[str, WorldActivation] = {}
        self.policies: Dict[str, WorldPolicies] = {}
        self.bindings: Dict[str, Set[str]] = {}
        self.decisions: Dict[str, List[str]] = {}
        self.audit: Dict[str, WorldAuditLog] = {}
        self.domain_states: Dict[str, DomainState] = {}

    async def create_world(self, world: Dict) -> None:
        self.worlds[world["id"]] = world
        self.audit.setdefault(world["id"], WorldAuditLog()).entries.append({"event": "world_created", "world": world})

    async def list_worlds(self) -> List[Dict]:
        return list(self.worlds.values())

    async def get_world(self, world_id: str) -> Optional[Dict]:
        return self.worlds.get(world_id)

    async def update_world(self, world_id: str, data: Dict) -> None:
        if world_id not in self.worlds:
            raise KeyError(world_id)
        self.worlds[world_id].update(data)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "world_updated", "world": self.worlds[world_id]})

    async def delete_world(self, world_id: str) -> None:
        self.worlds.pop(world_id, None)
        self.activations.pop(world_id, None)
        self.policies.pop(world_id, None)
        self.bindings.pop(world_id, None)
        self.decisions.pop(world_id, None)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "world_deleted"})

    async def add_policy(self, world_id: str, policy: Policy) -> int:
        wp = self.policies.setdefault(world_id, WorldPolicies())
        version = max(wp.versions.keys(), default=0) + 1
        wp.versions[version] = policy
        if wp.default is None:
            wp.default = version
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "policy_added", "version": version})
        return version

    async def list_policies(self, world_id: str) -> List[Dict]:
        wp = self.policies.get(world_id)
        if not wp:
            return []
        return [{"version": v} for v in sorted(wp.versions.keys())]

    async def get_policy(self, world_id: str, version: int) -> Optional[Policy]:
        wp = self.policies.get(world_id)
        if not wp:
            return None
        return wp.versions.get(version)

    async def set_default_policy(self, world_id: str, version: int) -> None:
        wp = self.policies.setdefault(world_id, WorldPolicies())
        if version not in wp.versions:
            raise KeyError(version)
        wp.default = version
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "policy_default_set", "version": version})

    async def get_default_policy(self, world_id: str) -> Optional[Policy]:
        wp = self.policies.get(world_id)
        if not wp or wp.default is None:
            return None
        return wp.versions.get(wp.default)

    async def default_policy_version(self, world_id: str) -> int:
        wp = self.policies.get(world_id)
        if not wp or wp.default is None:
            return 0
        return wp.default

    async def add_bindings(self, world_id: str, strategies: Iterable[str]) -> None:
        b = self.bindings.setdefault(world_id, set())
        b.update(strategies)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "bindings_added", "strategies": list(strategies)})

    async def list_bindings(self, world_id: str) -> List[str]:
        return sorted(self.bindings.get(world_id, set()))

    async def set_decisions(self, world_id: str, strategies: List[str]) -> None:
        self.decisions[world_id] = list(strategies)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "decisions_set", "strategies": list(strategies)})

    async def get_decisions(self, world_id: str) -> List[str]:
        return list(self.decisions.get(world_id, []))

    async def get_activation(self, world_id: str, strategy_id: str | None = None, side: str | None = None) -> Dict:
        act = self.activations.get(world_id)
        if not act:
            return {"version": 0, "state": {}}
        if strategy_id is not None and side is not None:
            data = act.state.get(strategy_id, {}).get(side, {})
            return {"version": act.version, **data}
        return {"version": act.version, "state": act.state}

    async def update_activation(self, world_id: str, payload: Dict) -> tuple[int, Dict]:
        act = self.activations.setdefault(world_id, WorldActivation())
        act.version += 1
        strategy_id = payload["strategy_id"]
        side = payload["side"]
        entry = {
            "active": payload.get("active", False),
            "weight": payload.get("weight", 1.0),
            "freeze": payload.get("freeze", False),
            "drain": payload.get("drain", False),
            "effective_mode": payload.get("effective_mode"),
            "run_id": payload.get("run_id"),
            "ts": payload.get("ts")
            or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        etag = f"act:{world_id}:{strategy_id}:{side}:{act.version}"
        entry["etag"] = etag
        act.state.setdefault(strategy_id, {})[side] = entry
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
            {"event": "activation_updated", "version": act.version, "strategy_id": strategy_id, "side": side, **entry}
        )
        return act.version, entry

    def _ensure_domain_state(self, world_id: str) -> DomainState:
        return self.domain_states.setdefault(world_id, DomainState())

    def _touch_activation_entries(
        self,
        world_id: str,
        *,
        freeze: Optional[bool] = None,
        drain: Optional[bool] = None,
        effective_mode: Optional[str] = None,
        run_id: Optional[str] = None,
        ts: Optional[str] = None,
    ) -> List[Dict]:
        act = self.activations.get(world_id)
        if not act or not act.state:
            return []
        timestamp = ts or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        act.version += 1
        version = act.version
        updates: List[Dict] = []
        for strategy_id, sides in act.state.items():
            for side, entry in sides.items():
                if freeze is not None:
                    entry["freeze"] = freeze
                if drain is not None:
                    entry["drain"] = drain
                if effective_mode is not None:
                    entry["effective_mode"] = effective_mode
                if run_id is not None:
                    entry["run_id"] = run_id
                entry["ts"] = timestamp
                entry["version"] = version
                entry["etag"] = f"act:{world_id}:{strategy_id}:{side}:{version}"
                updates.append({"strategy_id": strategy_id, "side": side, **entry})
        return updates

    async def apply_transition(self, world_id: str, transition: DomainTransition) -> Tuple[DomainState, List[Dict]]:
        if not transition.run_id:
            raise ValueError("run_id is required for domain transitions")
        phase = transition.phase.lower()
        state = self._ensure_domain_state(world_id)
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        updates: List[Dict] = []

        if phase == "freeze":
            target = _normalize_domain(transition.target)
            if state.run_id and state.run_id != transition.run_id and state.pending:
                raise RuntimeError("transition already in progress")
            if state.pending and state.pending != target:
                raise RuntimeError("different target already pending")
            state.previous = state.current
            state.pending = target
            state.run_id = transition.run_id
            state.freeze = True
            state.drain = True
            state.phase = "freeze"
            state.last_transition_at = now
            updates = self._touch_activation_entries(
                world_id,
                freeze=True,
                drain=True,
                effective_mode=_effective_mode_for_domain(state.current),
                run_id=transition.run_id,
                ts=now,
            )
        elif phase == "switch":
            if state.run_id and state.run_id != transition.run_id:
                raise RuntimeError("transition run_id mismatch")
            if state.pending:
                if transition.target and _normalize_domain(transition.target) != state.pending:
                    raise RuntimeError("switch target mismatch")
                state.previous = state.current
                state.current = state.pending
                state.pending = None
            else:
                if transition.target and _normalize_domain(transition.target) != state.current:
                    raise RuntimeError("no pending transition for target")
            state.freeze = True
            state.drain = True
            state.phase = "switch"
            state.last_transition_at = now
            updates = self._touch_activation_entries(
                world_id,
                freeze=True,
                drain=True,
                effective_mode=_effective_mode_for_domain(state.current),
                run_id=transition.run_id,
                ts=now,
            )
        elif phase == "unfreeze":
            if state.run_id and state.run_id != transition.run_id:
                raise RuntimeError("transition run_id mismatch")
            state.freeze = False
            state.drain = False
            state.phase = "steady"
            state.last_transition_at = now
            updates = self._touch_activation_entries(
                world_id,
                freeze=False,
                drain=False,
                effective_mode=_effective_mode_for_domain(state.current),
                run_id=transition.run_id,
                ts=now,
            )
            state.run_id = None
        elif phase == "rollback":
            # Roll back to explicit target or previous domain if available
            target = _normalize_domain(transition.target or state.previous or state.current)
            prev = state.current
            state.current = target
            state.pending = None
            state.previous = prev
            state.freeze = False
            state.drain = False
            state.phase = "rollback"
            state.last_transition_at = now
            state.run_id = None
            updates = self._touch_activation_entries(
                world_id,
                freeze=False,
                drain=False,
                effective_mode=_effective_mode_for_domain(state.current),
                run_id=transition.run_id,
                ts=now,
            )
        else:
            raise ValueError(f"unsupported transition phase: {transition.phase}")

        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
            {
                "event": "domain_transition",
                "phase": state.phase,
                "run_id": transition.run_id,
                "current": state.current,
                "previous": state.previous,
                "pending": state.pending,
                "freeze": state.freeze,
                "drain": state.drain,
                "ts": now,
            }
        )
        return state, updates

    async def get_domain_state(self, world_id: str) -> DomainState:
        return self._ensure_domain_state(world_id)

    async def get_audit(self, world_id: str) -> List[Dict]:
        return list(self.audit.get(world_id, WorldAuditLog()).entries)


__all__ = [
    'WorldActivation',
    'WorldPolicies',
    'WorldAuditLog',
    'DomainState',
    'DomainTransition',
    'Storage',
]
