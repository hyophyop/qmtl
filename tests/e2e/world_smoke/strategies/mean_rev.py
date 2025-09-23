"""Minimal world-smoke strategy runner aligned to WS-first APIs.

This script writes per-world artifacts and, when QMTL is importable,
executes a no-op Strategy via Runner.offline to exercise the SDK path
without relying on deprecated dry-run modes.
"""

import os, json, time, pathlib, random
from datetime import datetime

ARTIFACT_DIR = pathlib.Path(os.environ.get("ARTIFACT_DIR", ".artifacts/world_smoke"))


def _now_iso():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def run_sdk_mode(world_id: str, duration_sec: int = 5):
    """
    QMTL이 없을 때의 최소 스모크: world_id 라벨로 분리된 아티팩트 생성.
    """
    run_id = f"{world_id}-{int(time.time())}"
    out_dir = ARTIFACT_DIR / world_id / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 가짜 리턴 시계열 생성 & 간단 지표(이동평균 교차)로 signal 생성
    random.seed(42)
    prices = [100.0]
    for _ in range(120):
        prices.append(prices[-1] * (1.0 + random.uniform(-0.001, 0.001)))
    fast = sum(prices[-5:]) / 5.0
    slow = sum(prices[-20:]) / 20.0
    signal = 1 if fast < slow else 0

    # 아티팩트 기록
    (out_dir / "run.json").write_text(
        json.dumps(
            {
                "world_id": world_id,
                "run_id": run_id,
                "mode": "sdk-fallback",
                "signal": signal,
                "ts": _now_iso(),
            },
            indent=2,
        )
    )

    # 로그
    (out_dir / "log.txt").write_text(
        f"[{_now_iso()}] SDK fallback run; world={world_id}, signal={signal}\n"
    )

    # 잠깐 대기(서비스 모드와 비슷한 타임라인)
    time.sleep(max(1, duration_sec))


def run_qmtl_mode(world_id: str, duration_sec: int = 5):
    """
    QMTL Runner가 있을 때의 간단 실행.
    WS-first API에 맞춰 Runner.offline을 사용합니다.
    QMTL이 import 불가하면 SDK fallback으로 대체합니다.
    """
    try:
        from qmtl.runtime.sdk import Runner, Strategy  # type: ignore
    except Exception:
        run_sdk_mode(world_id, duration_sec)
        return

    class _NoopStrategy(Strategy):  # minimal offline-compatible strategy
        def setup(self) -> None:  # noqa: D401
            # 의도적으로 실행 노드를 추가하지 않습니다.
            # Runner.offline은 실행 가능한 노드가 없으면 곧바로 종료합니다.
            return None

    run_id = f"{world_id}-{int(time.time())}"
    out_dir = ARTIFACT_DIR / world_id / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 오프라인 모드로 간단 실행 (실제 노드 실행 없음)
    try:
        Runner.offline(_NoopStrategy)
    except Exception:
        # 어떤 이유로든 실패하면 SDK fallback 수행
        run_sdk_mode(world_id, duration_sec)
        return

    # 실행 메타 저장
    (out_dir / "run.json").write_text(
        json.dumps(
            {
                "world_id": world_id,
                "run_id": run_id,
                "mode": "qmtl-offline",
                "ts": _now_iso(),
            },
            indent=2,
        )
    )
    (out_dir / "log.txt").write_text(
        f"[{_now_iso()}] QMTL offline finished; world={world_id}\n"
    )
    # 타임라인 유사 대기
    time.sleep(max(1, duration_sec))


if __name__ == "__main__":
    world_id = os.environ.get("WORLD_ID") or "default"
    duration = int(os.environ.get("DURATION_SEC", "5"))
    try:
        run_qmtl_mode(world_id, duration)
    except Exception:
        # 어떠한 이유로든 실패하면 SDK fallback이라도 수행
        run_sdk_mode(world_id, duration)
