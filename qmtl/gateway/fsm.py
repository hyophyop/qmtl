from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

import redis.asyncio as redis
from xstate.machine import Machine

if TYPE_CHECKING:
    from .database import Database


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
        await self.redis.hset(f"strategy:{strategy_id}", "state", state)
        await self.database.insert_strategy(strategy_id, meta)
        await self.database.append_event(strategy_id, f"INIT:{state}")

    async def transition(self, strategy_id: str, event: str) -> str:
        current = await self.get(strategy_id)
        if current is None:
            raise ValueError("unknown strategy")
        state = self.machine.state_from(current)
        new_state = self.machine.transition(state, event)
        await self.redis.hset(f"strategy:{strategy_id}", "state", new_state.value)
        await self.database.set_status(strategy_id, new_state.value)
        await self.database.append_event(strategy_id, event)
        return new_state.value

    async def get(self, strategy_id: str) -> Optional[str]:
        data = await self.redis.hget(f"strategy:{strategy_id}", "state")
        if data is None:
            # Recover from DB if available
            state = await self.database.get_status(strategy_id)
            if state is None:
                return None
            await self.redis.hset(f"strategy:{strategy_id}", "state", state)
            return state
        return data.decode() if isinstance(data, bytes) else data
