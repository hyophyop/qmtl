from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, Mapping

import httpx


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    action: str
    method: str | None
    path: str | None
    status_code: int | None
    ok: bool
    skipped: bool = False
    reason: str | None = None
    response: Any | None = None


@dataclass(frozen=True, slots=True)
class CampaignRunConfig:
    world_id: str
    strategy_id: str | None = None
    execute: bool = False
    execute_evaluate: bool = False
    timeout_sec: float = 10.0
    max_actions: int = 50
    base_url: str = "http://localhost:8000"


class CampaignExecutor:
    """Execute Phase 4 campaign tick recommendations via HTTP.

    This is designed to be embedded (library style) and invoked by a thin CLI.
    It uses the campaign tick endpoint as the SSOT for the "next step", and
    optionally executes some of those steps.
    """

    def __init__(self, *, base_url: str, timeout_sec: float = 10.0) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._timeout_sec = float(timeout_sec)

    @property
    def base_url(self) -> str:
        return self._base_url

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float | bool] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> tuple[int, Any]:
        url = f"{self._base_url}{path}"
        normalized_params: dict[str, str | int | float | bool] | None = None
        if params is not None:
            normalized_params = {str(k): v for k, v in params.items() if v is not None}
        with httpx.Client(timeout=self._timeout_sec) as client:
            resp = client.request(method, url, params=normalized_params, json=json_body)
        if resp.status_code == 204:
            return resp.status_code, None
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, resp.text

    def tick(self, *, world_id: str, strategy_id: str | None = None) -> dict[str, Any]:
        params: dict[str, str | int | float | bool] = {}
        if strategy_id:
            params["strategy_id"] = str(strategy_id)
        status, payload = self._request(
            "POST",
            f"/worlds/{world_id}/campaign/tick",
            params=params or None,
            json_body={},
        )
        if status >= 400 or status == 0 or not isinstance(payload, dict):
            raise RuntimeError(f"campaign tick failed: status={status}, payload={payload}")
        return payload

    @staticmethod
    def _materialize_evaluate_payload(template: Mapping[str, Any], *, strategy_id: str) -> dict[str, object]:
        payload: dict[str, object] = json.loads(json.dumps(dict(template)))
        payload["strategy_id"] = strategy_id
        metrics = payload.get("metrics")
        if isinstance(metrics, dict):
            if "<strategy_id>" in metrics and strategy_id not in metrics:
                metrics[strategy_id] = metrics.pop("<strategy_id>")
            payload["metrics"] = metrics
        return payload

    def execute_tick(self, cfg: CampaignRunConfig) -> tuple[dict[str, Any], list[ExecutionResult]]:
        tick = self.tick(world_id=cfg.world_id, strategy_id=cfg.strategy_id)
        raw_actions = tick.get("actions")
        if not isinstance(raw_actions, list):
            raise RuntimeError("invalid tick response: missing actions")

        results: list[ExecutionResult] = []
        for raw in raw_actions[: max(0, int(cfg.max_actions or 0))]:
            if not isinstance(raw, dict):
                continue
            action = str(raw.get("action") or "")
            suggested_method = raw.get("suggested_method")
            suggested_endpoint = raw.get("suggested_endpoint")
            suggested_params = raw.get("suggested_params")
            suggested_body = raw.get("suggested_body")

            if not cfg.execute:
                results.append(
                    ExecutionResult(
                        action=action,
                        method=str(suggested_method) if suggested_method else None,
                        path=str(suggested_endpoint) if suggested_endpoint else None,
                        status_code=None,
                        ok=True,
                        skipped=True,
                        reason="dry_run",
                    )
                )
                continue

            if not suggested_method or not suggested_endpoint:
                results.append(
                    ExecutionResult(
                        action=action,
                        method=None,
                        path=None,
                        status_code=None,
                        ok=True,
                        skipped=True,
                        reason="no_suggested_call",
                    )
                )
                continue

            method = str(suggested_method).upper()
            path = str(suggested_endpoint)
            params: dict[str, str | int | float | bool] | None = None
            if isinstance(suggested_params, Mapping):
                params = {
                    str(k): bool(v) if isinstance(v, bool) else int(v) if isinstance(v, int) and not isinstance(v, bool) else float(v) if isinstance(v, float) else str(v)
                    for k, v in suggested_params.items()
                    if v is not None
                }

            body: dict[str, object] | None = None
            if method in {"POST", "PUT"}:
                if isinstance(suggested_body, Mapping):
                    if action == "evaluate":
                        if not cfg.execute_evaluate:
                            results.append(
                                ExecutionResult(
                                    action=action,
                                    method=method,
                                    path=path,
                                    status_code=None,
                                    ok=True,
                                    skipped=True,
                                    reason="execute_evaluate_disabled",
                                )
                            )
                            continue
                        sid = cfg.strategy_id or str(raw.get("strategy_id") or "")
                        if not sid:
                            results.append(
                                ExecutionResult(
                                    action=action,
                                    method=method,
                                    path=path,
                                    status_code=None,
                                    ok=False,
                                    skipped=True,
                                    reason="missing_strategy_id",
                                )
                            )
                            continue
                        body = self._materialize_evaluate_payload(suggested_body, strategy_id=sid)
                    else:
                        body = {str(k): v for k, v in suggested_body.items() if v is not None}
                else:
                    body = {}

            status_code, resp_payload = self._request(method, path, params=params, json_body=body)
            ok = 200 <= int(status_code) < 300
            results.append(
                ExecutionResult(
                    action=action,
                    method=method,
                    path=path,
                    status_code=int(status_code),
                    ok=ok,
                    skipped=False,
                    response=resp_payload,
                )
            )
        return tick, results


class LockFile:
    """Cross-platform best-effort lock based on atomic file create."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._fd: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(self.path), flags)
        except FileExistsError:
            return False
        self._fd = fd
        payload = f"pid={os.getpid()} ts={int(time.time())}\n"
        os.write(fd, payload.encode())
        os.fsync(fd)
        return True

    def release(self) -> None:
        fd = self._fd
        self._fd = None
        try:
            if fd is not None:
                os.close(fd)
        finally:
            try:
                self.path.unlink(missing_ok=True)
            except Exception:
                return

    def __enter__(self) -> "LockFile":
        if not self.acquire():
            raise RuntimeError(f"lock already held: {self.path}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def default_lock_path(world_id: str) -> Path:
    base = Path(tempfile.gettempdir())
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in world_id)
    return base / f"qmtl-campaign-loop-{safe}.lock"
