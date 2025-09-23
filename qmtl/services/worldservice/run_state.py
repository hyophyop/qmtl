"""State tracking helpers for world service apply flows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, MutableMapping, Sequence


class ApplyStage(str, Enum):
    """Well-defined phases for the world apply state machine."""

    REQUESTED = "requested"
    FREEZE = "freeze"
    SWITCH = "switch"
    UNFREEZE = "unfreeze"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


@dataclass(slots=True)
class ApplyRunState:
    """In-memory representation of the progress of an apply invocation."""

    run_id: str
    active: list[str] = field(default_factory=list)
    stage: ApplyStage = ApplyStage.REQUESTED
    completed: bool = False
    sequence: int = 0

    def mark(
        self,
        stage: ApplyStage,
        *,
        completed: bool | None = None,
        active: Sequence[str] | None = None,
    ) -> None:
        """Update the current stage metadata for the run."""

        if active is not None:
            self.active = list(active)
        self.stage = stage
        if completed is not None:
            self.completed = completed

    def next_sequence(self) -> int:
        """Advance the activation event sequence counter."""

        self.sequence += 1
        return self.sequence


class ApplyRunRegistry:
    """Track active apply runs and provide per-world synchronization locks."""

    def __init__(self) -> None:
        self._runs: Dict[str, ApplyRunState] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def get(self, world_id: str) -> ApplyRunState | None:
        return self._runs.get(world_id)

    def start(self, world_id: str, run_id: str, active: Sequence[str]) -> ApplyRunState:
        state = ApplyRunState(run_id=run_id, active=list(active))
        self._runs[world_id] = state
        return state

    def remove(self, world_id: str) -> None:
        self._runs.pop(world_id, None)

    def lock_for(self, world_id: str) -> asyncio.Lock:
        lock = self._locks.get(world_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[world_id] = lock
        return lock

    @property
    def runs(self) -> MutableMapping[str, ApplyRunState]:
        return self._runs

    @property
    def locks(self) -> MutableMapping[str, asyncio.Lock]:
        return self._locks


__all__ = ["ApplyRunRegistry", "ApplyRunState", "ApplyStage"]
