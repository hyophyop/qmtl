from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

import logging
import redis.asyncio as redis
from xstate.machine import Machine

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
            await self.redis.hset(f"strategy:{strategy_id}", "state", state)
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
            await self.redis.hset(
                f"strategy:{strategy_id}", "state", new_state.value
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
            data = await self.redis.hget(f"strategy:{strategy_id}", "state")
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
                await self.redis.hset(f"strategy:{strategy_id}", "state", state)
            except redis.RedisError as exc:
                logger.exception("Redis error caching strategy %s", strategy_id)
            return state
        return data.decode() if isinstance(data, bytes) else data
