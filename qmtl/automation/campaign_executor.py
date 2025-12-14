from __future__ import annotations

from dataclasses import dataclass
import json
import math
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

    Metrics note
    ------------
    Campaign tick actions for `evaluate` require strategy metrics. In early
    implementations, we source metrics by reusing the latest available evaluated
    metrics for the strategy (prefer matching stage; fallback to any stage).
    This keeps the executor lightweight and swappable for future producers.

    When available, we also enrich (or fallback to) Risk Signal Hub snapshots to
    provide portfolio-level risk/stress inputs at evaluation time.
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
    def _parse_iso(ts: object) -> float:
        text = str(ts or "").strip()
        if not text:
            return 0.0
        candidate = text
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            from datetime import datetime

            parsed = datetime.fromisoformat(candidate)
            return float(parsed.timestamp())
        except Exception:
            return 0.0

    def _pick_latest_run_id(
        self,
        runs: list[dict[str, Any]],
        *,
        stage: str | None,
    ) -> str | None:
        target_stage = str(stage or "").lower().strip() or None

        def _rank(run: dict[str, Any]) -> tuple[float, float]:
            return (
                self._parse_iso(run.get("updated_at")),
                self._parse_iso(run.get("created_at")),
            )

        def _is_evaluated(run: dict[str, Any]) -> bool:
            status = str(run.get("status") or "").lower().strip()
            if status == "evaluated":
                return True
            metrics = run.get("metrics")
            if isinstance(metrics, dict):
                return bool(metrics)
            return metrics is not None

        candidates = [r for r in runs if isinstance(r, dict) and _is_evaluated(r)]
        if not candidates:
            return None
        if target_stage:
            stage_candidates = [
                r
                for r in candidates
                if str(r.get("stage") or "").lower().strip() == target_stage
            ]
            if stage_candidates:
                candidates = stage_candidates
        best = max(candidates, key=_rank)
        rid = str(best.get("run_id") or "").strip()
        return rid or None

    def _fetch_latest_metrics(
        self,
        *,
        world_id: str,
        strategy_id: str,
        stage: str | None,
    ) -> dict[str, Any] | None:
        status, runs_payload = self._request(
            "GET",
            f"/worlds/{world_id}/strategies/{strategy_id}/runs",
        )
        if status >= 400 or status == 0 or not isinstance(runs_payload, list):
            return None

        runs: list[dict[str, Any]] = [r for r in runs_payload if isinstance(r, dict)]
        run_id = self._pick_latest_run_id(runs, stage=stage)
        if not run_id:
            return None

        status, metrics_payload = self._request(
            "GET",
            f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/metrics",
        )
        if status >= 400 or status == 0 or not isinstance(metrics_payload, Mapping):
            return None

        metrics = metrics_payload.get("metrics")
        if metrics is None:
            return None
        if isinstance(metrics, Mapping):
            return {str(k): v for k, v in metrics.items()}
        return None

    def _fetch_risk_hub_snapshot(
        self,
        *,
        world_id: str,
        stage: str | None,
        actor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any] | None:
        params: dict[str, str | int | float | bool] = {"expand": True, "limit": int(limit)}
        if stage:
            params["stage"] = str(stage)
        if actor:
            params["actor"] = str(actor)
        status, payload = self._request(
            "GET",
            f"/risk-hub/worlds/{world_id}/snapshots/latest",
            params=params,
        )
        if status >= 400 or status == 0 or not isinstance(payload, Mapping):
            return None
        return dict(payload)

    @staticmethod
    def _coerce_float_series(source: Any) -> list[float] | None:
        if isinstance(source, (list, tuple)):
            try:
                series = [float(v) for v in source]
            except Exception:
                return None
            clean = [v for v in series if math.isfinite(v)]
            return clean or None
        return None

    @classmethod
    def _extract_returns_from_realized(
        cls,
        realized: Any,
        *,
        strategy_id: str,
    ) -> list[float] | None:
        if realized is None:
            return None
        if isinstance(realized, Mapping):
            for key in (strategy_id, str(strategy_id), "live_returns", "returns"):
                if key in realized:
                    series = cls._coerce_float_series(realized.get(key))
                    if series is not None:
                        return series
            nested = realized.get("strategies")
            if isinstance(nested, Mapping) and strategy_id in nested:
                series = cls._coerce_float_series(nested.get(strategy_id))
                if series is not None:
                    return series
        return cls._coerce_float_series(realized)

    @staticmethod
    def _extract_stress_for_strategy(stress_payload: Any, *, strategy_id: str) -> dict[str, Any] | None:
        if stress_payload is None:
            return None
        if isinstance(stress_payload, Mapping):
            direct = stress_payload.get(strategy_id)
            if isinstance(direct, Mapping):
                return dict(direct)
            nested = stress_payload.get("strategies")
            if isinstance(nested, Mapping):
                bucket = nested.get(strategy_id)
                if isinstance(bucket, Mapping):
                    return dict(bucket)
            if any(isinstance(v, Mapping) for v in stress_payload.values()):
                return dict(stress_payload)
        return None

    @staticmethod
    def _lookup_covariance(covariance: Mapping[str, Any], a: str, b: str) -> float | None:
        for sep in (",", ":"):
            key = f"{a}{sep}{b}"
            if key in covariance:
                try:
                    value = float(covariance[key])
                except Exception:
                    value = None
                if value is not None and math.isfinite(value):
                    return value
                return None
            rev = f"{b}{sep}{a}"
            if rev in covariance:
                try:
                    value = float(covariance[rev])
                except Exception:
                    value = None
                if value is not None and math.isfinite(value):
                    return value
                return None
        return None

    @staticmethod
    def _candidate_weight_from_snapshot(snapshot: Mapping[str, Any]) -> float | None:
        constraints = snapshot.get("constraints")
        if isinstance(constraints, Mapping):
            raw = None
            for key in ("candidate_weight", "candidate_weight_default", "candidate_weight_pct"):
                if key in constraints:
                    raw = constraints.get(key)
                    if key == "candidate_weight_pct":
                        if isinstance(raw, bool):
                            raw = None
                        elif isinstance(raw, (int, float, str)):
                            try:
                                raw = float(raw) / 100.0
                            except (TypeError, ValueError):
                                raw = None
                        else:
                            raw = None
                    break
            if raw is not None:
                try:
                    value = float(raw)
                except Exception:
                    value = None
                if value is not None and math.isfinite(value) and 0.0 < value <= 1.0:
                    return float(value)
        return None

    def _baseline_from_covariance(
        self,
        *,
        weights: Mapping[str, Any],
        covariance: Mapping[str, Any],
    ) -> dict[str, float] | None:
        if not weights or not covariance:
            return None
        w_sum = 0.0
        for value in weights.values():
            try:
                w_sum += float(value)
            except Exception:
                return None
        if w_sum <= 0:
            return None
        norm_weights = {str(k): float(v) / w_sum for k, v in weights.items() if isinstance(v, (int, float))}
        variance = 0.0
        sids = list(norm_weights.keys())
        for a in sids:
            for b in sids:
                cov_val = self._lookup_covariance(covariance, a, b)
                if cov_val is None:
                    continue
                variance += norm_weights.get(a, 0.0) * norm_weights.get(b, 0.0) * float(cov_val)
        if not (variance >= 0.0 and math.isfinite(variance)):
            return None
        z_var_99 = 2.33
        var_99 = math.sqrt(variance) * z_var_99
        if not math.isfinite(var_99):
            return None
        return {"var_99": float(var_99), "es_99": float(var_99) * 1.2}

    def _incremental_var_es_from_covariance(
        self,
        *,
        weights: Mapping[str, Any],
        covariance: Mapping[str, Any],
        candidate_id: str,
        candidate_weight: float,
        baseline: Mapping[str, Any],
    ) -> dict[str, float] | None:
        if candidate_id in weights:
            return None
        base_var = baseline.get("var_99")
        base_es = baseline.get("es_99")
        if not isinstance(base_var, (int, float)) or not isinstance(base_es, (int, float)):
            return None
        alpha = float(candidate_weight)
        if not math.isfinite(alpha) or alpha <= 0.0:
            return None
        if alpha > 1.0:
            alpha = 1.0
        if self._lookup_covariance(covariance, candidate_id, candidate_id) is None:
            return None

        scaled_existing: dict[str, float] = {}
        if alpha < 1.0:
            for sid, weight in weights.items():
                if not isinstance(weight, (int, float)):
                    continue
                if weight == 0:
                    continue
                scaled = float(weight) * (1.0 - alpha)
                if scaled != 0:
                    scaled_existing[str(sid)] = scaled

        new_weights = dict(scaled_existing)
        new_weights[candidate_id] = alpha
        with_candidate = self._baseline_from_covariance(weights=new_weights, covariance=covariance)
        if with_candidate is None:
            return None
        with_var = with_candidate.get("var_99")
        with_es = with_candidate.get("es_99")
        if not isinstance(with_var, (int, float)) or not isinstance(with_es, (int, float)):
            return None
        return {
            "candidate_weight": float(alpha),
            "incremental_var_99": float(with_var) - float(base_var),
            "incremental_es_99": float(with_es) - float(base_es),
        }

    @staticmethod
    def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = dict(base)
        for key, value in overlay.items():
            if key in out and isinstance(out.get(key), Mapping) and isinstance(value, Mapping):
                out[key] = CampaignExecutor._deep_merge(out[key], value)
            else:
                out[key] = value
        return out

    def _metrics_from_risk_hub(
        self,
        *,
        world_id: str,
        strategy_id: str,
        stage: str | None,
    ) -> dict[str, Any] | None:
        snapshot = self._fetch_risk_hub_snapshot(world_id=world_id, stage=stage)
        if not snapshot:
            return None
        derived: dict[str, Any] = {}

        realized = snapshot.get("realized_returns")
        live_returns = self._extract_returns_from_realized(realized, strategy_id=strategy_id)
        if live_returns is not None:
            diagnostics = dict(derived.get("diagnostics") or {})
            diagnostics["live_returns"] = live_returns
            diagnostics.setdefault("live_returns_source", "risk_hub")
            derived["diagnostics"] = diagnostics

        stress_payload = snapshot.get("stress")
        stress = self._extract_stress_for_strategy(stress_payload, strategy_id=strategy_id)
        if stress is not None:
            derived["stress"] = stress

        weights = snapshot.get("weights")
        covariance = snapshot.get("covariance")
        if isinstance(weights, Mapping) and isinstance(covariance, Mapping) and covariance:
            baseline = self._baseline_from_covariance(weights=weights, covariance=covariance)
            if baseline:
                candidate_weight = self._candidate_weight_from_snapshot(snapshot)
                if candidate_weight is None:
                    candidate_weight = 1.0 / float(max(1, len(weights)) + 1)
                risk_metrics = self._incremental_var_es_from_covariance(
                    weights=weights,
                    covariance=covariance,
                    candidate_id=strategy_id,
                    candidate_weight=candidate_weight,
                    baseline=baseline,
                )
                if risk_metrics:
                    risk = dict(derived.get("risk") or {})
                    risk["incremental_var_99"] = risk_metrics.get("incremental_var_99")
                    risk["incremental_es_99"] = risk_metrics.get("incremental_es_99")
                    risk["candidate_weight"] = risk_metrics.get("candidate_weight")
                    derived["risk"] = risk

                    diagnostics = dict(derived.get("diagnostics") or {})
                    extra = dict(diagnostics.get("extra_metrics") or {})
                    extra.setdefault("portfolio_baseline_var_99", baseline.get("var_99"))
                    extra.setdefault("portfolio_baseline_es_99", baseline.get("es_99"))
                    extra.setdefault("risk_hub_snapshot_version", snapshot.get("version"))
                    diagnostics["extra_metrics"] = extra
                    derived["diagnostics"] = diagnostics

        return derived or None

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
                        stage = str(suggested_body.get("stage") or raw.get("stage") or "").strip() or None
                        base_metrics = self._fetch_latest_metrics(
                            world_id=cfg.world_id,
                            strategy_id=sid,
                            stage=stage,
                        )
                        hub_metrics = self._metrics_from_risk_hub(
                            world_id=cfg.world_id,
                            strategy_id=sid,
                            stage=stage,
                        )
                        derived_metrics: dict[str, Any] | None
                        if base_metrics and hub_metrics:
                            derived_metrics = self._deep_merge(base_metrics, hub_metrics)
                        elif base_metrics:
                            derived_metrics = base_metrics
                        elif hub_metrics:
                            derived_metrics = hub_metrics
                        else:
                            derived_metrics = None

                        if not derived_metrics:
                            results.append(
                                ExecutionResult(
                                    action=action,
                                    method=method,
                                    path=path,
                                    status_code=None,
                                    ok=True,
                                    skipped=True,
                                    reason="missing_metrics_source",
                                )
                            )
                            continue
                        body = self._materialize_evaluate_payload(suggested_body, strategy_id=sid)
                        body["metrics"] = {sid: derived_metrics}
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
