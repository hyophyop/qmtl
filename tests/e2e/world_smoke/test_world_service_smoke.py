# tests/e2e/world_smoke/test_world_service_smoke.py
import os, json, base64, subprocess, urllib.request

import pytest
from pathlib import Path


# ---------- 공통 유틸 ----------

def _read_metrics(metrics_url: str) -> str:
    with urllib.request.urlopen(metrics_url, timeout=3) as r:
        return r.read().decode("utf-8", errors="ignore")


def _post_yaml(url: str, yml_path: Path):
    # 참고: 실제 WorldService 스펙에 맞게 바꾸세요.
    # 여기선 단순 업로드 예시(예: POST /worlds with YAML body)
    data = yml_path.read_bytes()
    req = urllib.request.Request(url.rstrip("/") + "/worlds", data=data, method="POST")
    req.add_header("Content-Type", "application/x-yaml")
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status in (200, 201)


def _decode_jwt_no_verify(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise AssertionError("invalid JWT format")
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    payload = base64.urlsafe_b64decode(payload_b64 + padding)
    return json.loads(payload.decode())


def _gateway_subscribe(gateway_base: str, world_id: str) -> dict:
    url = f"{gateway_base.rstrip('/')}/events/subscribe"
    data = json.dumps({
        "world_id": world_id,
        "strategy_id": "e2e-world-smoke",
        "topics": ["activation", "policy"],
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200
        return json.loads(r.read().decode("utf-8"))


# ---------- SDK 모드 ----------

@pytest.mark.order(1)
def test_sdk_mode_world_isolated_artifacts(artifact_dir: Path):
    if os.environ.get("WS_MODE", "sdk") != "sdk":
        pytest.skip("not in sdk mode")

    # 두 월드로 동일 전략 1회씩 짧게 실행
    for wid in ("prod-us-equity", "sandbox-crypto"):
        subprocess.check_call(
            ["python", "tests/e2e/world_smoke/scripts/run_world.py", wid, "3"],
            env={**os.environ, "ARTIFACT_DIR": str(artifact_dir)},
        )

    # 월드별 아티팩트 폴더가 분리되어 생성되었는지 확인
    prod_runs = list((artifact_dir / "prod-us-equity").glob("*/run.json"))
    sand_runs = list((artifact_dir / "sandbox-crypto").glob("*/run.json"))
    assert prod_runs and sand_runs, "run.json not found for worlds"

    # 각 run.json에 world_id 라벨 확인
    with open(prod_runs[-1], "r") as f:
        prod_meta = json.load(f)
    with open(sand_runs[-1], "r") as f:
        sand_meta = json.load(f)

    assert prod_meta["world_id"] == "prod-us-equity"
    assert sand_meta["world_id"] == "sandbox-crypto"


# ---------- 서비스 모드 ----------

@pytest.mark.order(2)
def test_service_mode_register_worlds(svc_env, worlds):
    # 월드 정의를 서비스에 등록 (스펙에 맞게 조정)
    _post_yaml(svc_env["worlds"], worlds["prod"])
    _post_yaml(svc_env["worlds"], worlds["sandbox"])


@pytest.mark.order(3)
def test_service_mode_gateway_event_tokens(svc_env):
    # 각 월드에 대해 Gateway /events/subscribe 토큰 획득 및 클레임 확인
    for wid in ("prod-us-equity", "sandbox-crypto"):
        try:
            sub = _gateway_subscribe(svc_env["gateway"], wid)
        except Exception:
            pytest.skip("gateway /events/subscribe not reachable")
        assert "token" in sub and sub["token"], "missing token"
        claims = _decode_jwt_no_verify(sub["token"])
        assert claims.get("world_id") == wid


@pytest.mark.order(4)
def test_service_mode_metrics_have_world_labels(svc_env):
    metrics_url = svc_env.get("metrics")
    if not metrics_url:
        pytest.skip("QMTL_METRICS_URL not set")
    try:
        body = _read_metrics(metrics_url)
    except Exception:
        pytest.skip("metrics endpoint not reachable")
    # 최소한 world 라벨이 두 개 다수 관찰되는지 확인(패턴은 환경에 맞게 구체화)
    assert 'world_id="prod-us-equity"' in body or 'world="prod-us-equity"' in body
    assert 'world_id="sandbox-crypto"' in body or 'world="sandbox-crypto"' in body
