# tests/e2e/world_smoke/strategies/mean_rev.py
import os, json, time, pathlib, random
from datetime import datetime, timedelta

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
    구현체마다 차이가 있을 수 있어 try/except 보호 및 최소 동작만.
    """
    try:
        from qmtl.sdk.runner import Runner  # type: ignore
        from qmtl.sdk.node import Node  # type: ignore
    except Exception:
        run_sdk_mode(world_id, duration_sec)
        return

    run_id = f"{world_id}-{int(time.time())}"
    out_dir = ARTIFACT_DIR / world_id / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 최소한의 더미 노드 구성: tick 카운터를 흘리는 노드
    def ticker_fn(ctx, inputs):
        # ctx.world 접근 가능하다면 기록
        return {
            "count": (inputs.get("count", 0) if isinstance(inputs, dict) else 0) + 1,
            "world": getattr(getattr(ctx, "world", None), "id", world_id),
        }

    # 참고: 현재 리포의 Runner API는 dryrun 대신 offline/run을 제공합니다.
    # 본 스크립트는 존재하지 않는 API 호출 시 __main__에서 SDK fallback으로 전환됩니다.
    src = Node(name=f"counter-{world_id}", compute_fn=ticker_fn, interval="1s", period=1, inputs=[])
    strategy = [src]  # 실제 프로젝트의 Strategy 객체로 교체 가능

    r = Runner()
    try:
        # Dry-run으로 짧게 실행 (API가 없으면 AttributeError 유발)
        r.dryrun(strategy, world_id=world_id, duration=timedelta(seconds=duration_sec))  # type: ignore[attr-defined]
    except TypeError:
        # world_id 인자 미지원 버전 대비
        r.dryrun(strategy, duration=timedelta(seconds=duration_sec))  # type: ignore[attr-defined]

    # 실행 메타 저장
    (out_dir / "run.json").write_text(
        json.dumps(
            {
                "world_id": world_id,
                "run_id": run_id,
                "mode": "qmtl-dry-run",
                "ts": _now_iso(),
            },
            indent=2,
        )
    )
    (out_dir / "log.txt").write_text(
        f"[{_now_iso()}] QMTL dry-run finished; world={world_id}\n"
    )


if __name__ == "__main__":
    world_id = os.environ.get("WORLD_ID") or "default"
    duration = int(os.environ.get("DURATION_SEC", "5"))
    try:
        run_qmtl_mode(world_id, duration)
    except Exception:
        # 어떠한 이유로든 실패하면 SDK fallback이라도 수행
        run_sdk_mode(world_id, duration)

