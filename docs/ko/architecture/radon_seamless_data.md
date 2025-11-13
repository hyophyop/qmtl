# Seamless Data Provider Radon 계획

## 범위
- 대상 모듈: `qmtl/runtime/sdk/seamless_data_provider.py`(생성자, 도메인 게이트, 페치 오케스트레이션, 범위 계산).
- 이 계획으로 정리할 이슈: #1468, #1482, #1491.

## 현재 radon 스냅샷
| 파일 | 최악 CC 블록 (등급 / 점수) | MI | Raw SLOC | 비고 |
| --- | --- | --- | --- | --- |
| `runtime/sdk/seamless_data_provider.py` | `__init__` — D / 21 (이전에는 E) | 0.00 (C) | 2 719 | 생성자가 설정 로딩, SLA 결정, 지문 정책, 도메인 게이트 연결을 모두 담당.

## 리팩터링 전략
1. 설정·프리셋 해석을 `_build_conformance_defaults`, `_init_backfill_policy`, `_configure_fingerprint_mode` helper로 분리해 `__init__`은 오케스트레이션만 맡습니다.
2. `DomainGateEvaluator`를 dataclass 기반 팩토리로 만들어 필요한 의존성만 주입하고, `self` 상태 의존을 줄입니다.
3. `_fetch_seamless`를 페치 플랜 계산, 아티팩트 선택, 결과 정합 단계로 나눠 각 단계를 결정론적 단위 테스트로 보호합니다.
4. 캐시/스토리지/백필/라이브 폴백 파이프라인을 문서화해 확장성을 높입니다.

## 검증 체크리스트
- `uv run --with radon -m radon cc -s qmtl/runtime/sdk/seamless_data_provider.py`
- `uv run --with radon -m radon mi -s qmtl/runtime/sdk/seamless_data_provider.py`
- `uv run -m pytest -W error -n auto qmtl/runtime/sdk/tests/test_seamless_data_provider.py`
- `uv run mkdocs build`

## 예상 결과
이 계획을 구현한 PR이 머지되면 **Fixes #1468, Fixes #1482, Fixes #1491**가 자동으로 처리됩니다.
