# WorldService 할당·리밸런서 Radon 계획

## 범위
- 대상 모듈: `qmtl/services/worldservice/services.py`, `worldservice/rebalancing/multi.py`, `worldservice/storage/persistent.py`.
- 이 계획으로 정리할 이슈: #1478, #1479, #1489, #1498.

## 현재 radon 스냅샷
| 파일 | 최악 CC 블록 (등급 / 점수) | MI | Raw SLOC | 비고 |
| --- | --- | --- | --- | --- |
| `services/worldservice/rebalancing/multi.py` | `_derive_strategy_targets` — C / 13 | 53.85 (A) | 122 | 멀티 월드 비율 계산이 검증·수학·스토리지 호출을 한 함수에서 처리.
| `services/worldservice/services.py` | `_handle_existing_allocation_run` — B / 7 | 27.30 (A) | 374 | 오케스트레이터가 줄었지만 여전히 검증·락·저장을 혼합.
| `services/worldservice/storage/persistent.py` | `create` / `add_policy` — B / 7 | 13.39 (B) | 1 047 | 스토리지 helper가 SLOC 가이드를 넘어서고 MI가 하한에 근접.

## 리팩터링 전략
1. 할당 업데이트를 단계별(페이로드 정규화 → 플랜 생성 → 저장 → 실행) helper로 분리해 `WorldService.upsert_allocations`는 단계 조정만 담당하게 합니다.
2. 비율 리밸런싱 수식을 재사용 가능한 계산기로 옮겨 `MultiWorldProportionalRebalancer.plan`이 입출력 연결에 집중하도록 만듭니다.
3. `PersistentStorage`를 세계 메타데이터/정책/할당 전용 저장소로 쪼개거나, 최소한 대형 메서드를 스탠드얼론 helper로 옮겨 MI 20+를 회복합니다.
4. 새 경계를 반영하는 단위·통합 테스트를 추가해 플랜·저장 변경이 회귀 없이 진행되도록 합니다.

## 검증 체크리스트
- `uv run --with radon -m radon cc -s qmtl/services/worldservice/{services,rebalancing/multi}.py`
- `uv run --with radon -m radon mi -s qmtl/services/worldservice/storage/persistent.py`
- `uv run -m pytest -W error -n auto qmtl/services/worldservice/tests`
- `uv run mkdocs build`

## 예상 결과
이 계획을 바탕으로 한 최종 PR이 머지되면 **Fixes #1478, Fixes #1479, Fixes #1489, Fixes #1498**가 자동으로 처리됩니다.
