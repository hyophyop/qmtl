from __future__ import annotations

import base64
import json
import uuid
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from qmtl.gateway.world_client import WorldServiceClient

from .dependencies import GatewayDependencyProvider

WorldCall = Callable[[WorldServiceClient, dict[str, str]], Awaitable[Any]]


def _build_world_headers(request: Request) -> tuple[dict[str, str], str]:
    headers: dict[str, str] = {}
    auth = request.headers.get("authorization")
    if auth:
        headers["Authorization"] = auth
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1]
            try:
                parts = token.split(".")
                if len(parts) > 1:
                    payload_b64 = parts[1]
                    padding = "=" * (-len(payload_b64) % 4)
                    payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode()
                    claims = json.loads(payload_json)
                    sub = claims.get("sub")
                    if sub is not None:
                        headers["X-Caller-Sub"] = str(sub)
                    headers["X-Caller-Claims"] = json.dumps(claims)
            except Exception:
                pass
    roles = request.headers.get("x-world-roles")
    if roles:
        headers["X-World-Roles"] = roles
    cid = uuid.uuid4().hex
    headers["X-Correlation-ID"] = cid
    return headers, cid


async def _proxy_world_call(
    request: Request,
    client: WorldServiceClient,
    func: WorldCall,
    *,
    response_builder: Callable[[Any, dict[str, str]], Response] | None = None,
) -> Response:
    headers, cid = _build_world_headers(request)
    data = await func(client, headers)
    base_headers = {"X-Correlation-ID": cid}
    builder = response_builder or (
        lambda payload, hdrs: JSONResponse(payload, headers=dict(hdrs))
    )
    return builder(data, dict(base_headers))


def create_router(deps: GatewayDependencyProvider) -> APIRouter:
    router = APIRouter()

    @router.post("/worlds")
    async def create_world(
        payload: dict,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.create_world(payload, headers=headers),
        )

    @router.get("/worlds")
    async def list_worlds(
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request, world_client, lambda client, headers: client.list_worlds(headers=headers)
        )

    @router.get("/worlds/{world_id}")
    async def get_world(
        world_id: str,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.get_world(world_id, headers=headers),
        )

    @router.put("/worlds/{world_id}")
    async def put_world(
        world_id: str,
        payload: dict,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.put_world(world_id, payload, headers=headers),
        )

    @router.delete(
        "/worlds/{world_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
    )
    async def delete_world(
        world_id: str,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Response:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.delete_world(world_id, headers=headers),
            response_builder=lambda _data, headers: Response(
                status_code=status.HTTP_204_NO_CONTENT, headers=headers
            ),
        )

    @router.post("/worlds/{world_id}/policies")
    async def post_world_policy(
        world_id: str,
        payload: dict,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.post_policy(world_id, payload, headers=headers),
        )

    @router.get("/worlds/{world_id}/policies")
    async def get_world_policies(
        world_id: str,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.get_policies(world_id, headers=headers),
        )

    @router.post("/worlds/{world_id}/set-default")
    async def post_world_set_default(
        world_id: str,
        payload: dict,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.set_default_policy(
                world_id, payload, headers=headers
            ),
        )

    @router.post("/worlds/{world_id}/bindings")
    async def post_world_bindings(
        world_id: str,
        payload: dict,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.post_bindings(world_id, payload, headers=headers),
        )

    @router.get("/worlds/{world_id}/bindings")
    async def get_world_bindings(
        world_id: str,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.get_bindings(world_id, headers=headers),
        )

    @router.post("/worlds/{world_id}/decisions")
    async def post_world_decisions(
        world_id: str,
        payload: dict,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.post_decisions(world_id, payload, headers=headers),
        )

    @router.put("/worlds/{world_id}/activation")
    async def put_world_activation(
        world_id: str,
        payload: dict,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.put_activation(world_id, payload, headers=headers),
        )

    @router.get("/worlds/{world_id}/audit")
    async def get_world_audit(
        world_id: str,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.get_audit(world_id, headers=headers),
        )

    @router.get("/worlds/{world_id}/decide")
    async def get_world_decide(
        world_id: str,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        def _response(result: Any, headers: dict[str, str]) -> Response:
            data, stale = result
            resp_headers = dict(headers)
            if stale:
                resp_headers["Warning"] = "110 - Response is stale"
                resp_headers["X-Stale"] = "true"
            return JSONResponse(data, headers=resp_headers)

        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.get_decide(world_id, headers=headers),
            response_builder=_response,
        )

    @router.get("/worlds/{world_id}/activation")
    async def get_world_activation(
        world_id: str,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        strategy_id = request.query_params.get("strategy_id", "")
        side = request.query_params.get("side", "")

        def _response(result: Any, headers: dict[str, str]) -> Response:
            data, stale = result
            resp_headers = dict(headers)
            if stale:
                resp_headers["Warning"] = "110 - Response is stale"
                resp_headers["X-Stale"] = "true"
            return JSONResponse(data, headers=resp_headers)

        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.get_activation(
                world_id, strategy_id, side, headers=headers
            ),
            response_builder=_response,
        )

    @router.get("/worlds/{world_id}/{topic}/state_hash")
    async def get_world_state_hash(
        world_id: str,
        topic: str,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.get_state_hash(world_id, topic, headers=headers),
        )

    @router.post("/worlds/{world_id}/evaluate")
    async def post_world_evaluate(
        world_id: str,
        payload: dict,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.post_evaluate(world_id, payload, headers=headers),
        )

    @router.post("/worlds/{world_id}/apply")
    async def post_world_apply(
        world_id: str,
        payload: dict,
        request: Request,
        enforce_live_guard: bool = Depends(deps.provide_enforce_live_guard),
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Any:
        if enforce_live_guard and request.headers.get("X-Allow-Live") != "true":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "E_PERMISSION_DENIED",
                    "message": "live trading not allowed",
                },
            )
        return await _proxy_world_call(
            request,
            world_client,
            lambda client, headers: client.post_apply(world_id, payload, headers=headers),
        )

    return router


__all__ = ["create_router"]
