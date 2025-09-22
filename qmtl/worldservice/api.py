from __future__ import annotations

from fastapi import FastAPI

from .controlbus_producer import ControlBusProducer
from .routers import (
    create_activation_router,
    create_bindings_router,
    create_policies_router,
    create_validations_router,
    create_worlds_router,
)
from .schemas import (
    ApplyAck,
    ApplyPlan,
    ApplyRequest,
    ApplyResponse,
    EvaluateRequest,
    PolicyRequest,
    World,
)
from .services import WorldService
from .storage import Storage


def create_app(*, bus: ControlBusProducer | None = None, storage: Storage | None = None) -> FastAPI:
    app = FastAPI()
    store = storage or Storage()
    service = WorldService(store=store, bus=bus)
    app.state.apply_locks = service.apply_locks
    app.state.apply_runs = service.apply_runs
    app.include_router(create_worlds_router(service))
    app.include_router(create_policies_router(service))
    app.include_router(create_bindings_router(service))
    app.include_router(create_activation_router(service))
    app.include_router(create_validations_router(service))
    return app


__all__ = [
    'World',
    'PolicyRequest',
    'ApplyPlan',
    'EvaluateRequest',
    'ApplyRequest',
    'ApplyResponse',
    'ApplyAck',
    'create_app',
]
