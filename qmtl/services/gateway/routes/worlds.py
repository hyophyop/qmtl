from __future__ import annotations

import base64
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Sequence

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from qmtl.services.gateway.world_client import WorldServiceClient

from .dependencies import GatewayDependencyProvider

WorldCall = Callable[[WorldServiceClient, dict[str, str]], Awaitable[Any]]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorldRoute:
    """Declarative route configuration for WorldService proxies."""

    method: str
    path: str
    client_method: str
    path_params: Sequence[str] = ()
    include_payload: bool = False
    query_params: Sequence[str] = ()
    stale_response: bool = False
    enforce_live_guard: bool = False
    status_code: int | None = None
    response_builder: Callable[[Any, dict[str, str]], Response] | None = None


_STALE_WARNING = "110 - Response is stale"


def _stale_response_builder(result: Any, headers: dict[str, str]) -> Response:
    data, stale = result
    resp_headers = dict(headers)
    if stale:
        resp_headers["Warning"] = _STALE_WARNING
        resp_headers["X-Stale"] = "true"
    return JSONResponse(data, headers=resp_headers)


def _no_content_response(_: Any, headers: dict[str, str]) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


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
    try:
        data = await func(client, headers)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        detail = _extract_worldservice_detail(exc.response)
        log_level = logging.INFO if status_code == status.HTTP_404_NOT_FOUND else logging.WARNING
        logger.log(
            log_level,
            "WorldService proxy %s %s returned %s (cid=%s): %s",
            request.method,
            request.url.path,
            status_code,
            cid,
            detail,
        )
        raise HTTPException(
            status_code=status_code,
            detail=detail,
            headers={"X-Correlation-ID": cid},
        ) from None
    except httpx.RequestError as exc:
        logger.warning(
            "WorldService proxy request failed for %s %s (cid=%s): %s",
            request.method,
            request.url.path,
            cid,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WorldService unavailable",
            headers={"X-Correlation-ID": cid},
        ) from None

    base_headers = {"X-Correlation-ID": cid}
    builder = response_builder or (
        lambda payload, hdrs: JSONResponse(payload, headers=dict(hdrs))
    )
    return builder(data, dict(base_headers))


def _extract_worldservice_detail(response: httpx.Response) -> Any:
    try:
        payload = response.json()
        if isinstance(payload, dict) and "detail" in payload:
            return payload["detail"]
        return payload
    except Exception:
        text = response.text
        return text or "WorldService request failed"


async def _execute_world_call(
    config: WorldRoute,
    request: Request,
    payload: dict | None,
    world_client: WorldServiceClient,
    path_params: Mapping[str, str],
    enforce_live_guard: bool | None,
) -> Response:
    if config.enforce_live_guard and enforce_live_guard:
        if request.headers.get("X-Allow-Live") != "true":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "E_PERMISSION_DENIED",
                    "message": "live trading not allowed",
                },
            )

    args: list[Any] = [path_params[param] for param in config.path_params]

    for query_param in config.query_params:
        args.append(request.query_params.get(query_param, ""))

    if config.include_payload:
        args.append(payload)

    async def _call(client: WorldServiceClient, headers: dict[str, str]) -> Any:
        method = getattr(client, config.client_method)
        return await method(*args, headers=headers)

    response_builder = config.response_builder
    if response_builder is None and config.stale_response:
        response_builder = _stale_response_builder

    return await _proxy_world_call(
        request,
        world_client,
        _call,
        response_builder=response_builder,
    )


def _register_world_route(
    router: APIRouter,
    deps: GatewayDependencyProvider,
    config: WorldRoute,
) -> None:
    # Validate client method exists early to surface typos.
    getattr(WorldServiceClient, config.client_method)

    route_kwargs: dict[str, Any] = {}
    if config.status_code is not None:
        route_kwargs["status_code"] = config.status_code
        if config.status_code == status.HTTP_204_NO_CONTENT:
            route_kwargs["response_model"] = None

    registrar = getattr(router, config.method.lower())

    if config.include_payload and config.enforce_live_guard:

        @registrar(config.path, **route_kwargs)
        async def endpoint(
            payload: dict,
            request: Request,
            enforce_live_guard: bool = Depends(deps.provide_enforce_live_guard),
            world_client: WorldServiceClient = Depends(deps.provide_world_client),
        ) -> Response:
            return await _execute_world_call(
                config,
                request,
                payload,
                world_client,
                request.path_params,
                enforce_live_guard,
            )

    elif config.include_payload:

        @registrar(config.path, **route_kwargs)
        async def endpoint(
            payload: dict,
            request: Request,
            world_client: WorldServiceClient = Depends(deps.provide_world_client),
        ) -> Response:
            return await _execute_world_call(
                config,
                request,
                payload,
                world_client,
                request.path_params,
                None,
            )

    elif config.enforce_live_guard:

        @registrar(config.path, **route_kwargs)
        async def endpoint(
            request: Request,
            enforce_live_guard: bool = Depends(deps.provide_enforce_live_guard),
            world_client: WorldServiceClient = Depends(deps.provide_world_client),
        ) -> Response:
            return await _execute_world_call(
                config,
                request,
                None,
                world_client,
                request.path_params,
                enforce_live_guard,
            )

    else:

        @registrar(config.path, **route_kwargs)
        async def endpoint(
            request: Request,
            world_client: WorldServiceClient = Depends(deps.provide_world_client),
        ) -> Response:
            return await _execute_world_call(
                config,
                request,
                None,
                world_client,
                request.path_params,
                None,
            )


WORLD_ROUTES: tuple[WorldRoute, ...] = (
    WorldRoute("post", "/rebalancing/plan", "post_rebalance_plan", include_payload=True),
    WorldRoute("post", "/worlds", "create_world", include_payload=True),
    WorldRoute("get", "/worlds", "list_worlds"),
    WorldRoute(
        "get",
        "/worlds/{world_id}",
        "get_world",
        path_params=("world_id",),
    ),
    WorldRoute(
        "get",
        "/worlds/{world_id}/describe",
        "describe_world",
        path_params=("world_id",),
    ),
    WorldRoute(
        "put",
        "/worlds/{world_id}",
        "put_world",
        path_params=("world_id",),
        include_payload=True,
    ),
    WorldRoute(
        "delete",
        "/worlds/{world_id}",
        "delete_world",
        path_params=("world_id",),
        status_code=status.HTTP_204_NO_CONTENT,
        response_builder=_no_content_response,
    ),
    WorldRoute(
        "post",
        "/worlds/{world_id}/policies",
        "post_policy",
        path_params=("world_id",),
        include_payload=True,
    ),
    WorldRoute(
        "get",
        "/worlds/{world_id}/policies",
        "get_policies",
        path_params=("world_id",),
    ),
    WorldRoute(
        "post",
        "/worlds/{world_id}/set-default",
        "set_default_policy",
        path_params=("world_id",),
        include_payload=True,
    ),
    WorldRoute(
        "post",
        "/worlds/{world_id}/bindings",
        "post_bindings",
        path_params=("world_id",),
        include_payload=True,
    ),
    WorldRoute(
        "get",
        "/worlds/{world_id}/bindings",
        "get_bindings",
        path_params=("world_id",),
    ),
    WorldRoute(
        "post",
        "/worlds/{world_id}/decisions",
        "post_decisions",
        path_params=("world_id",),
        include_payload=True,
    ),
    WorldRoute(
        "put",
        "/worlds/{world_id}/activation",
        "put_activation",
        path_params=("world_id",),
        include_payload=True,
    ),
    WorldRoute(
        "get",
        "/worlds/{world_id}/audit",
        "get_audit",
        path_params=("world_id",),
    ),
    WorldRoute(
        "get",
        "/worlds/{world_id}/decide",
        "get_decide",
        path_params=("world_id",),
        stale_response=True,
    ),
    WorldRoute(
        "get",
        "/worlds/{world_id}/activation",
        "get_activation",
        path_params=("world_id",),
        query_params=("strategy_id", "side"),
        stale_response=True,
    ),
    WorldRoute(
        "get",
        "/worlds/{world_id}/{topic}/state_hash",
        "get_state_hash",
        path_params=("world_id", "topic"),
    ),
    WorldRoute(
        "post",
        "/worlds/{world_id}/evaluate",
        "post_evaluate",
        path_params=("world_id",),
        include_payload=True,
    ),
    WorldRoute(
        "post",
        "/worlds/{world_id}/apply",
        "post_apply",
        path_params=("world_id",),
        include_payload=True,
        enforce_live_guard=True,
    ),
)


def create_router(deps: GatewayDependencyProvider) -> APIRouter:
    router = APIRouter()

    for route in WORLD_ROUTES:
        _register_world_route(router, deps, route)

    return router


__all__ = ["create_router"]
