# 데이터 정규화·백필 Radon 계획

## 범위

- 대상 경로: 실시간·히스토리 IO 및 심리스 SDK 전반의 **데이터 정규화·백필·아티팩트 퍼블리시** 경로.
- 주요 모듈:
  - `qmtl/runtime/io/ccxt_live_feed.py`
  - `qmtl/runtime/io/artifact.py`
  - `qmtl/runtime/io/historyprovider.py`
  - `qmtl/runtime/io/seamless_provider.py`
  - `qmtl/runtime/io/ccxt_rate_limiter.py`
  - `qmtl/runtime/io/ccxt_fetcher.py`
  - `qmtl/runtime/sdk/seamless_data_provider.py`
- 이 계획으로 정리할 이슈:
  - #1550 (데이터 정규화·백필 경로 복잡도 개선)
  - #1574 (인벤토리 및 설계 문서)
  - #1575 (runtime/io 리팩터링)
  - #1576 (runtime/sdk 리팩터링)

## 현재 radon 스냅샷 (핵심 C급 함수)

2025-11-16 기준, `uv run --with radon -m radon cc -s qmtl/runtime/io qmtl/runtime/sdk/seamless_data_provider.py` 출력에서 **데이터 정규화·백필·퍼블리시와 직결된 C급 함수**만 추린 요약입니다.

| 경로 | 심볼 | 역할 | CC 등급 / 점수 |
| --- | --- | --- | --- |
| `runtime/io/ccxt_live_feed.py:74` | `CcxtProLiveFeed.subscribe` | ccxt.pro 라이브 피드 구독·재접속, 모드별 스트림 orchestrator | C / 19 |
| `runtime/io/ccxt_live_feed.py:222` | `CcxtProLiveFeed._normalize_records` | OHLCV/체결 레코드 정규화·중복 제거 | C / 16 |
| `runtime/io/ccxt_live_feed.py:283` | `CcxtProLiveFeed._get_or_create_exchange` | ccxt.pro 인스턴스 생성·마켓 메타데이터 로딩 | C / 13 |
| `runtime/io/artifact.py:67` | `ArtifactRegistrar.publish` | 정규화된 프레임 아티팩트 퍼블리시·메타데이터 기록 | C / 11 |
| `runtime/io/historyprovider.py:59` | `QuestDBBackend.write_rows` | QuestDB 백엔드에 정규화된 행 일괄 쓰기 | C / 11 |
| `runtime/io/seamless_provider.py:185` | `DataFetcherAutoBackfiller.backfill` | 히스토리 백필 orchestration (DataFetcher 기반) | C / 12 |
| `runtime/io/ccxt_rate_limiter.py:177` | `get_limiter` | ccxt 호출용 rate limiter 구성·선택 | C / 16 |
| `runtime/io/ccxt_fetcher.py:258` | `CcxtOHLCVFetcher.fetch` | ccxt OHLCV 페치·재시도·정규화 | C / 15 |
| `runtime/sdk/seamless_data_provider.py:1116` | `SeamlessDataProvider._extract_context` | compute_context / world / as_of 정규화 및 요청 컨텍스트 생성 | C / 17 |
| `runtime/sdk/seamless_data_provider.py:1809` | `SeamlessDataProvider._handle_artifact_publication` | 퍼블리시 호출·fingerprint 계산·메타데이터 정규화 | C / 19 |
| `runtime/sdk/seamless_data_provider.py:1297` | `SeamlessDataProvider.fetch` | 심리스 fetch·백필·퍼블리시 최상위 orchestrator | C / 15 |
| `runtime/sdk/seamless_data_provider.py:1990` | `SeamlessDataProvider._resolve_publication_fingerprint` | 퍼블리케이션 fingerprint 정규화·모드별 선택 | C / 16 |
| `runtime/sdk/seamless_data_provider.py:166` | `_load_presets_document` | 심리스 프리셋 문서 로딩·정규화 | C / 16 |
| `runtime/sdk/seamless_data_provider.py:103` | `_read_publish_override_from_config` | 설정 기반 퍼블리시 오버라이드 해석 | C / 12 |
| `runtime/sdk/seamless_data_provider.py:2171` | `SeamlessDataProvider._resolve_downgrade` | 커버리지/도메인 기준 downgrade 결정 | C / 13 |
| `runtime/sdk/seamless_data_provider.py:2549` | `_RangeOperations._subtract_segment` | 커버리지 구간 차집합 계산 (백필 범위) | C / 11 |

위 함수들은 서로 다른 모듈에 흩어져 있지만, **데이터 정규화 → 백필 → 아티팩트 퍼블리시 / 커버리지 계산**이라는 하나의 긴 경로를 구성합니다.

## 공통 불량 패턴

주요 C급 함수들의 구현을 살펴보면, 다음과 같은 공통 문제가 반복됩니다.

- **역할 혼재**
  - 입력 소스/거래소/도메인 라우팅, 정규화, 검증, 백필/퍼블리시, 로깅/메트릭이 동일 메서드에 섞여 있습니다.
  - 예: `CcxtProLiveFeed.subscribe`, `SeamlessDataProvider.fetch`, `_handle_artifact_publication`.
- **정규화·매핑 로직 중복**
  - timestamp/world/domain/as_of/coverage 등 컨텍스트 필드 정규화 로직이 여러 곳에 흩어져 중복 정의됩니다.
  - 예: `_extract_context`, `_normalize_world_id`, `_normalize_domain` 조합과, 다른 모듈의 world/as_of 처리.
- **아티팩트 퍼블리시/registrar 통합 부족**
  - registrar publish 호출 경로가 IO 계층(`ArtifactRegistrar.publish`)과 SDK 계층(`_handle_artifact_publication`)에 걸쳐 중복·분산되어 있습니다.
  - 퍼블리케이션 fingerprint, coverage_bounds, manifest URI 처리 규칙도 분산되어 있어 추론이 어렵습니다.
- **커버리지·백필 구간 처리 복잡도**
  - `_RangeOperations._subtract_segment`, `DataFetcherAutoBackfiller.backfill` 등에서 커버리지 계산, 백필 범위 결정, 로깅/메트릭이 한 곳에 몰려 CC가 상승합니다.
- **테스트 관점에서의 경로 특정 어려움**
  - 큰 메서드 안에서 특정 분기를 직접 타기 어렵고, end-to-end 테스트에 의존하는 경향이 있어 회귀에 취약합니다.

## 목표 설계 (Strategy + 파이프라인 + 공통 헬퍼)

데이터 정규화·백필 경로의 복잡도를 낮추기 위해, 다음과 같은 재사용 가능한 설계 패턴을 채택합니다.

- **소스/거래소별 정규화 Strategy**
  - 예: `CcxtProLiveFeed` / `CcxtOHLCVFetcher` / Seamless SDK 모두에서, 소스별 정규화 전략을 인터페이스로 분리합니다.
  - 공통 인터페이스 예:
    - `normalize_ohlcv(raw: Any) -> NormalizedRecord`
    - `normalize_trade(raw: Any) -> NormalizedRecord`
    - `normalize_context(raw: Any) -> _RequestContext`
- **단계별 파이프라인 (Pipeline / Builder)**
  - “데이터 로드 → 정규화 → 검증 → 백필 → 아티팩트 퍼블리시 → 메트릭/로깅”을 작은 스텝으로 분해합니다.
  - 각 스텝은 **순수 함수 혹은 작은 helper 객체**로 두어, 단위 테스트로 직접 검증 가능하게 합니다.
  - 예:
    - IO 계층: `fetch_raw` → `normalize_records` → `write_rows` / `publish_artifact`.
    - SDK 계층: `_extract_context` → `fetch_or_backfill` → `_handle_artifact_publication` → `_finalize_metadata_metrics`.
- **공통 헬퍼/유틸 중앙화**
  - world/domain/as_of/min_coverage/max_lag 정규화, fingerprint 해석, coverage_bounds 계산, 아티팩트 크기·메트릭 기록 등을 공통 헬퍼로 이동합니다.
  - IO/SDK 양쪽에서 재사용 가능한 helper 모듈을 최소 하나 이상 도입하고, C급 함수에서는 orchestrator 역할만 남깁니다.
- **에러·로그 경로 분리**
  - 예외 처리·재시도(backoff)·다운그레이드 결정·로그/메트릭을 별도 헬퍼나 파이프라인 스텝으로 옮겨, 핵심 happy-path 로직의 분기 수를 줄입니다.

이 설계 원칙은 기존 문서들 (`radon_runtime_sdk.md`, `radon_seamless_data.md`, `seamless_data_provider_modularity.md`) 과 동일한 방향을 유지하면서, **정규화·백필 경로 전반을 가로지르는 cross-cutting 패턴**에 초점을 맞춥니다.

## 서브 이슈 및 진행 구조

이 계획은 다음 서브 이슈를 통해 단계적으로 구현됩니다.

- **#1574 — [docs] 데이터 정규화·백필 C급 함수 인벤토리 및 Strategy/파이프라인 설계 정리**
  - radon 기반 C급 함수 인벤토리(위 표)를 유지·보완합니다.
  - Strategy/파이프라인/공통 헬퍼 설계 가이드라인을 이 문서와 영어 버전에 정리합니다.
- **#1575 — [runtime/io] CcxtProLiveFeed.subscribe 정규화 파이프라인 도입**
  - `CcxtProLiveFeed` 계층의 C급 함수들을 대상으로, ccxt 라이브 피드 정규화·중복 제거·재접속 로직을 파이프라인/Strategy 기반으로 재구성합니다.
- **#1576 — [runtime/sdk] SeamlessDataProvider 정규화·백필/퍼블리시 파이프라인 도입**
  - `SeamlessDataProvider` 의 `_extract_context` / `fetch` / `_handle_artifact_publication` / `_resolve_publication_fingerprint` 등을 대상으로, 컨텍스트 정규화·백필·퍼블리시 파이프라인을 도입합니다.

각 서브 이슈는 **해당 모듈의 C급 함수들을 최소 B 등급 이하로 낮추고**, 이 문서에서 정의한 패턴과 정렬되도록 하는 것을 목표로 합니다.

## 검증 체크리스트

- radon 스냅샷
  - `uv run --with radon -m radon cc -s qmtl/runtime/io qmtl/runtime/sdk/seamless_data_provider.py`
  - 필요 시 diff 기반 확인:
    - `git diff --name-only origin/main... | rg '\\.py$' | xargs -r uv run --with radon -m radon cc -s -n C`
- 테스트
  - `PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1`
  - `uv run -m pytest -W error -n auto`
- 문서 빌드
  - `uv run mkdocs build`

위 체크리스트를 만족하는 PR들이 병합되면, #1550 에서 정의한 “데이터 정규화·백필 경로 복잡도 개선” 목표를 달성한 것으로 간주합니다.

