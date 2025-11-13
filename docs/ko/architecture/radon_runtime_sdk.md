# 런타임 SDK Radon 정비 계획

## 범위
- 대상 모듈: `qmtl/runtime/sdk/activation_manager.py`, `backtest_validation.py`, `conformance.py`, `execution_context.py`, `snapshot.py`, `qmtl/runtime/transforms/alpha_performance.py`.
- 이 계획으로 정리할 이슈: #1461, #1462, #1465, #1466, #1469, #1470, #1484, #1485, #1495, #1500.

## 현재 radon 스냅샷
| 파일 | 최악 CC 블록 (등급 / 점수) | MI | Raw SLOC | 비고 |
| --- | --- | --- | --- | --- |
| `runtime/sdk/activation_manager.py` | `_on_message` — C / 19 | 21.96 (A) | 261 | 메시지 팬아웃·게이트웨이 조정이 한 메서드에 집중.
| `runtime/sdk/backtest_validation.py` | `validate_backtest_data` — C / 12 | 51.78 (A) | 182 | 스키마 검증·스코어링·리포팅이 뒤섞여 있음.
| `runtime/sdk/conformance.py` | `_extract_schema_mapping` — C / 15 | 32.26 (A) | 304 | 타임스탬프 정규화와 스키마 추출이 강하게 결합.
| `runtime/sdk/execution_context.py` | `resolve_execution_context` — B / 10 (현재 A) | 76.60 (A) | 69 | 기준 이하지만 #1484 범위상 함께 추적.
| `runtime/sdk/snapshot.py` | `_record_snapshot_metrics` — B / 10 | 29.09 (A) | 437 | 메트릭 방출과 저장 로직이 섞여 있음.
| `runtime/transforms/alpha_performance.py` | `AlphaPerformanceNode` — A / 3 | 82.64 (A) | 78 | 지금은 단순하지만 #1500 요구에 포함.

## 리팩터링 전략
1. **활성화 팬아웃** – `_on_message`를 파서·구독 매처·실행 helper로 분리하고, 조정자는 결과만 결합하도록 단순화합니다.
2. **검증 파이프라인** – `BacktestDataValidator`를 스키마/순서/타임아웃/스코어링 단계별 순수 함수로 재편하여 각 단계를 개별 단위 테스트로 보호합니다.
3. **컨포먼스 정규화** – 타임스탬프 파싱, epoch 정렬, NaN 필터링을 helper 함수로 이관해 `_normalize_timestamps`는 상위 오케스트레이션만 담당하게 합니다.
4. **스냅샷·알파 헬퍼** – 메트릭 방출과 저장을 데코레이터/헬퍼 클래스로 분리해 B 이하를 유지합니다.
5. **문서·테스트** – 아키텍처 문서를 업데이트하고 SDK 테스트를 확장해 radon 게이트 전 회귀 안전망을 확보합니다.

## 검증 체크리스트
- `uv run --with radon -m radon cc -s qmtl/runtime/sdk/{activation_manager,backtest_validation,conformance,execution_context,snapshot}.py`
- `uv run --with radon -m radon cc -s qmtl/runtime/transforms/alpha_performance.py`
- `uv run --with radon -m radon mi -s qmtl/runtime/sdk qmtl/runtime/transforms/alpha_performance.py`
- `uv run -m pytest -W error -n auto qmtl/runtime/sdk/tests qmtl/runtime/transforms/tests`
- `uv run mkdocs build`

## 예상 결과
이 계획을 반영한 PR이 병합되면 다음 이슈가 자동으로 닫힙니다: **Fixes #1461, Fixes #1462, Fixes #1465, Fixes #1466, Fixes #1469, Fixes #1470, Fixes #1484, Fixes #1485, Fixes #1495, Fixes #1500.**
