# 컨트롤 플레인 Radon 계획 (게이트웨이 + DAG Manager)

## 범위
- 대상 모듈: `qmtl/services/gateway/{controlbus_consumer, shared_account_policy, strategy_submission.py}`, `strategy_manager.py`, `qmtl/services/dagmanager/{diff_service.py, grpc_server.py}`.
- 이 계획으로 정리할 이슈: #1471, #1472, #1473, #1475, #1477, #1488, #1496, #1497.

## 현재 radon 스냅샷
| 파일 | 최악 CC 블록 (등급 / 점수) | MI | Raw SLOC | 비고 |
| --- | --- | --- | --- | --- |
| `services/gateway/controlbus_consumer.py` | `_parse_kafka_message` — C / 15 | 24.61 (A) | 338 | 파싱·검증·디스패치가 뒤섞여 있음.
| `services/gateway/shared_account_policy.py` | `_accumulate_notional` — B / 9 | 35.19 (A) | 163 | 대부분 기준 내지만 #1496의 공유 정책 로직에 포함.
| `services/gateway/strategy_submission.py` | `_build_queue_outputs` — C / 14 | 30.66 (A) | 245 | 저장/큐 라우팅이 한 helper에 남아 있음.
| `services/gateway/strategy_manager.py` | `_inject_version_sentinel` — B / 7 | 24.61 (A) | 345 | 게이트웨이 메타 이슈 범위상 유지.
| `services/dagmanager/diff_service.py` | `_hash_compare` — C / 20 | 0.00 (C) | 906 | 대형 스트리밍 helper 때문에 MI 하락.
| `services/dagmanager/grpc_server.py` | `GetQueueStats` — C / 17 | 24.73 (A) | 348 | `DiffServiceServicer.Diff`는 B지만 다른 RPC 핸들러가 복잡.

## 리팩터링 전략
1. 게이트웨이 컨트롤 플로우를 요청 파싱, 검증, 부수 효과(스토리지/큐 쓰기) helper로 나눠 가벼운 async 함수가 조정하도록 만듭니다.
2. 정책/전략 dataclass를 도입해 `StrategySubmissionHelper`와 `StrategyManager`가 동일 검증 로직을 공유하게 합니다.
3. Diff 스트리밍을 큐 폴링 → diff 계산 → 스트림 write → 버스 publish 파이프라인으로 재구성해 helper 코루틴으로 중첩을 줄입니다.
4. DAG/게이트웨이 통합 테스트를 확장해 실패·재시도 경로를 커버한 뒤 리팩터링을 마무리합니다.

## 검증 체크리스트
- `uv run --with radon -m radon cc -s qmtl/services/gateway/{controlbus_consumer,shared_account_policy,strategy_submission,strategy_manager}.py`
- `uv run --with radon -m radon cc -s qmtl/services/dagmanager/{diff_service,grpc_server}.py`
- `uv run --with radon -m radon mi -s qmtl/services/dagmanager/diff_service.py`
- `uv run -m pytest -W error -n auto qmtl/services/gateway/tests qmtl/services/dagmanager/tests`

## 예상 결과
이 계획을 반영한 최종 PR이 머지되면 **Fixes #1471, Fixes #1472, Fixes #1473, Fixes #1475, Fixes #1477, Fixes #1488, Fixes #1496, Fixes #1497**가 자동으로 처리됩니다.
