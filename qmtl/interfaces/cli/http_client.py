from __future__ import annotations

import os
from typing import cast, Optional

import httpx
from httpx import _types as httpx_types

DEFAULT_GATEWAY_URL = "http://localhost:8000"


def gateway_url() -> str:
    return os.environ.get("QMTL_GATEWAY_URL", DEFAULT_GATEWAY_URL).rstrip("/")


def _normalize_params(params: dict[str, object] | None) -> httpx_types.QueryParamTypes | None:
    if params is None:
        return None
    filtered = {k: v for k, v in params.items() if v is not None}
    return cast(httpx_types.QueryParamTypes, filtered) if filtered else None


def http_request(
    method: str,
    path: str,
    params: Optional[dict[str, object]] = None,
    payload: Optional[dict[str, object]] = None,
) -> tuple[int, httpx_types.ResponseContent]:
    url = f"{gateway_url()}{path}"
    try:
        with httpx.Client(timeout=10.0) as client:
            if hasattr(client, method):
                http_method = getattr(client, method)
                try:
                    norm_params = _normalize_params(params)
                    if payload is None:
                        if norm_params is not None:
                            response = http_method(url, params=norm_params)
                        else:
                            response = http_method(url)
                    else:
                        if norm_params is not None:
                            response = http_method(url, params=norm_params, json=payload)
                        else:
                            response = http_method(url, json=payload)
                except TypeError:
                    response = client.request(method, url, params=_normalize_params(params), json=payload)
            else:
                response = client.request(method, url, params=_normalize_params(params), json=payload)
        if response.status_code == 204:
            return response.status_code, cast(httpx_types.ResponseContent, None)
        try:
            return response.status_code, cast(httpx_types.ResponseContent, response.json())
        except Exception:
            return response.status_code, response.text
    except Exception as e:  # pragma: no cover - network issues
        return 0, str(e)


def http_get(path: str, params: dict[str, object] | None = None) -> tuple[int, httpx_types.ResponseContent]:
    return http_request("get", path, params=params, payload=None)


def http_post(path: str, payload: dict[str, object] | None = None) -> tuple[int, httpx_types.ResponseContent]:
    return http_request("post", path, params=None, payload=payload)


def http_delete(path: str) -> tuple[int, httpx_types.ResponseContent]:
    return http_request("delete", path, params=None, payload=None)
