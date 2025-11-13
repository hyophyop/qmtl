# History Warmup Radon 계획

## 범위
- 대상 모듈: `qmtl/runtime/sdk/history_warmup_service.py`(웜업 오케스트레이션, 리플레이, strict 모드 강제).
- 이 계획으로 정리할 이슈: #1467, #1487, #1492.

## 현재 radon 스냅샷
| 파일 | 최악 CC 블록 (등급 / 점수) | MI | Raw SLOC | 비고 |
| --- | --- | --- | --- | --- |
| `runtime/sdk/history_warmup_service.py` | `_plan_strategy_warmup` — C / 15 | 11.78 (B) | 517 | 리플레이 헬퍼는 개선됐지만 플래너가 여전히 B 목표를 초과.

## 리팩터링 전략
1. 윈도 계산, 캐시 히트 감지, 노드 준비 단계를 helper 객체로 분리해 `_plan_strategy_warmup`은 순서만 조정합니다.
2. `replay_history` 경로는 타임스탬프 배치·재시도·메트릭 로직을 순수 helper로 옮겨 결정론적 단위 테스트를 추가합니다.
3. 웜업 상태 기계를 문서화해 선행 조건/리플레이/강제 단계가 어떻게 연결되는지 공유합니다.

## 검증 체크리스트
- `uv run --with radon -m radon cc -s qmtl/runtime/sdk/history_warmup_service.py`
- `uv run --with radon -m radon mi -s qmtl/runtime/sdk/history_warmup_service.py`
- `uv run -m pytest -W error -n auto qmtl/runtime/sdk/tests/test_history_warmup_service.py`
- `uv run mkdocs build`

## 예상 결과
최종 구현 PR이 머지되면 **Fixes #1467, Fixes #1487, Fixes #1492**가 자동으로 처리됩니다.
