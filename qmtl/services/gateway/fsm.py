from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Dict, Any, Awaitable, cast

import logging
import redis.asyncio as redis


class _State:
    """Lightweight state wrapper to mirror xstate's `.value` API."""

    def __init__(self, value: str) -> None:
        self.value = value


class Machine:
    """Minimal FSM engine compatible with the usage in this module.

    It supports an `initial_state` with a `.value` attribute and two methods:
    - `state_from(name)` -> returns a state object
    - `transition(state, event)` -> returns the next state object

    The machine is defined by a dictionary with the following structure:
    {
      "id": "strategy",
      "initial": "queued",
      "states": {
        "queued": {"on": {"PROCESS": "processing"}},
        "processing": {"on": {"COMPLETE": "completed", "FAIL": "failed"}},
        "failed": {"on": {"RETRY": "processing"}},
        "completed": {}
      }
    }
    """

    def __init__(self, definition: Dict) -> None:
        self._initial = str(definition.get("initial"))
        self._states: Dict[str, Dict] = dict(definition.get("states", {}))
        if self._initial not in self._states:
            raise ValueError("initial state must be defined in states")
        self.initial_state = _State(self._initial)

    def state_from(self, name: str) -> _State:
        if name not in self._states:
            raise ValueError(f"unknown state: {name}")
        return _State(name)

    def transition(self, state: _State, event: str) -> _State:
        current = state.value
        config = self._states.get(current)
        if not config:
            raise ValueError(f"unknown state: {current}")
        on = config.get("on", {})
        if event not in on:
            raise ValueError(f"invalid event {event!r} for state {current!r}")
        next_state = on[event]
        if next_state not in self._states:
            # Allow terminal next states that have empty config objects
            if next_state not in self._states:
                # If not present, treat as terminal with no transitions
                self._states[next_state] = {}
        return _State(next_state)

if TYPE_CHECKING:
    from .database import Database


logger = logging.getLogger(__name__)


class FSMError(Exception):
    """Base exception for FSM-related errors."""


class TransitionError(FSMError):
    """Raised when state transitions fail."""


@dataclass
class StrategyFSM:
    """Finite state machine managing strategy lifecycle."""

    redis: redis.Redis
    database: Database

    def __post_init__(self) -> None:
        self.machine = Machine(
            {
                "id": "strategy",
                "initial": "queued",
                "states": {
                    "queued": {"on": {"PROCESS": "processing"}},
                    "processing": {
                        "on": {"COMPLETE": "completed", "FAIL": "failed"}
                    },
                    "failed": {"on": {"RETRY": "processing"}},
                    "completed": {},
                },
            }
        )

    async def create(self, strategy_id: str, meta: Optional[dict]) -> None:
        state = self.machine.initial_state.value
        try:
            await cast(Awaitable[Any], self.redis.hset(f"strategy:{strategy_id}", "state", state))
        except redis.RedisError as exc:
            logger.exception("Redis error creating strategy %s", strategy_id)
            raise FSMError("failed to create strategy") from exc
        try:
            await self.database.insert_strategy(strategy_id, meta)
            await self.database.append_event(strategy_id, f"INIT:{state}")
        except Exception as exc:  # database errors
            logger.exception("Database error creating strategy %s", strategy_id)
            raise FSMError("failed to create strategy") from exc

    async def transition(self, strategy_id: str, event: str) -> str:
        try:
            current = await self.get(strategy_id)
        except FSMError as exc:
            logger.exception("Failed to load current state for %s", strategy_id)
            raise TransitionError("transition failed") from exc
        if current is None:
            raise ValueError("unknown strategy")
        state = self.machine.state_from(current)
        new_state = self.machine.transition(state, event)
        try:
            await cast(
                Awaitable[Any],
                self.redis.hset(f"strategy:{strategy_id}", "state", new_state.value),
            )
        except redis.RedisError as exc:
            logger.exception("Redis error during transition for %s", strategy_id)
            raise TransitionError("transition failed") from exc
        try:
            await self.database.set_status(strategy_id, new_state.value)
            await self.database.append_event(strategy_id, event)
        except Exception as exc:  # database errors
            logger.exception("Database error during transition for %s", strategy_id)
            raise TransitionError("transition failed") from exc
        return new_state.value

    async def get(self, strategy_id: str) -> Optional[str]:
        try:
            data = await cast(
                Awaitable[Any],
                self.redis.hget(f"strategy:{strategy_id}", "state"),
            )
        except redis.RedisError as exc:
            logger.exception(
                "Redis error retrieving strategy %s; falling back to DB", strategy_id
            )
            data = None
        if data is None:
            try:
                state = await self.database.get_status(strategy_id)
            except Exception as exc:  # database errors
                logger.exception(
                    "Database error retrieving strategy %s", strategy_id
                )
                raise FSMError("failed to retrieve strategy") from exc
            if state is None:
                return None
            try:
                await cast(
                    Awaitable[Any],
                    self.redis.hset(f"strategy:{strategy_id}", "state", state),
                )
            except redis.RedisError as exc:
                logger.exception("Redis error caching strategy %s", strategy_id)
            return state
        return data.decode() if isinstance(data, bytes) else data
