# Seamless Data Provider 구성 가이드

이 가이드는 Seamless Data Provider(SDP)를 실제 운영 환경에서 사용하기 위한 단계별 구성 방법과 운영 복잡도 평가, 그리고 사용성을 개선하기 위한 제안을 제공합니다.

## 1. 선행 준비 사항

1. **저장소 및 페치 계층** – QuestDB와 같은 히스토리 저장소와 이를 채우는 `DataFetcher`를 준비합니다. `EnhancedQuestDBProvider`는 저장소와 페치 계층을 우선순위 기반으로 조합해 투명한 조회를 수행합니다.【F:qmtl/docs/design/seamless_data_provider.md†L45-L90】【F:qmtl/qmtl/runtime/io/seamless_provider.py†L1-L108】
2. **분산 백필 코디네이터** – `qmtl.yml`의 `seamless.coordinator_url`을 설정하면 SDK가 자동으로 분산 백필 코디네이터와 통신합니다.【F:qmtl/docs/architecture/seamless_data_provider_v2.md†L38-L81】【F:qmtl/qmtl/runtime/sdk/seamless_data_provider.py†L421-L432】
3. **정합성 파이프라인** – 기본적으로 활성화된 `ConformancePipeline`은 스키마·시간 롤업과 리포트를 생성하며, 위반 시 요청을 차단합니다. 필요 시 `partial_ok=True`로 허용 모드를 사용할 수 있습니다.【F:qmtl/docs/design/seamless_data_provider.md†L31-L66】
4. **SLA 정책** – `SLAPolicy`를 구성하면 각 단계별 대기 시간을 추적하고 기준 초과 시 `SeamlessSLAExceeded` 예외 및 메트릭을 발행합니다.【F:qmtl/docs/design/seamless_data_provider.md†L66-L86】
5. **아티팩트/메트릭 수집** – 관측 지표(`seamless_sla_deadline_seconds`, `backfill_completion_ratio` 등)를 수집할 수 있도록 Prometheus 및 관련 대시보드를 구성합니다.【F:qmtl/docs/architecture/seamless_data_provider_v2.md†L82-L123】

## 2. 단계별 구성

1. **런타임 설정 갱신**
   ```yaml
   seamless:
     coordinator_url: https://seamless-coordinator.internal
     publish_fingerprint: true      # (선택) 아티팩트 지문 게시
     preview_fingerprint: false     # (선택) 프리뷰 지문 허용
     early_fingerprint: false       # (선택) 선행 지문 허용
   ```
   YAML 설정은 분산 백필 사용 여부와 지문 발행 정책을 제어해 감사 추적과 데이터 재현성을 강화합니다.【F:qmtl/qmtl/runtime/sdk/seamless_data_provider.py†L320-L373】【F:qmtl/qmtl/runtime/sdk/seamless_data_provider.py†L421-L432】

2. **프로바이더 인스턴스 생성**
   ```python
   from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
   from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy
   from myapp.fetchers import HistoricalFetcher, LiveFetcher

   provider = EnhancedQuestDBProvider(
       dsn="postgresql://questdb:8812/qmtl",
       table="market_data",
       fetcher=HistoricalFetcher(),
       live_fetcher=LiveFetcher(),
       strategy=DataAvailabilityStrategy.SEAMLESS,
       partial_ok=False,
   )
   ```
   `EnhancedQuestDBProvider`는 캐시 → 저장소 → 백필 → 라이브 데이터 순으로 요청을 평가하고, 설정된 전략에 따라 자동 백필 또는 부분 응답을 선택합니다.【F:qmtl/examples/seamless_data_provider_examples.py†L74-L112】【F:qmtl/qmtl/runtime/io/seamless_provider.py†L1-L213】

3. **SLA 및 정합성 정책 주입 (선택)**
   ```python
   from qmtl.runtime.sdk.sla import SLAPolicy
   from qmtl.runtime.sdk.conformance import ConformancePipeline

   provider = EnhancedQuestDBProvider(
       dsn="postgresql://questdb:8812/qmtl",
       fetcher=HistoricalFetcher(),
       strategy=DataAvailabilityStrategy.SEAMLESS,
       sla=SLAPolicy(total_deadline_ms=60000, storage_deadline_ms=5000),
       conformance=ConformancePipeline.partial_ok(True),
   )
   ```
   SLA 정책을 지정하면 메트릭과 예외 처리로 서비스 수준을 보장하고, 정합성 파이프라인 설정을 통해 데이터 품질을 제어할 수 있습니다.【F:qmtl/docs/design/seamless_data_provider.md†L31-L86】

4. **StreamInput에 연결**
   ```python
   from qmtl.runtime.nodes.stream_input import StreamInput

   stream = StreamInput(history_provider=provider)
   ```
   Seamless 프로바이더는 기존 노드와 완전 호환되며 추가 코드 변경 없이 교체 가능합니다.【F:qmtl/examples/seamless_data_provider_examples.py†L154-L219】

5. **관측 지표 및 로그 연동**
   - Prometheus에서 `seamless_sla_deadline_seconds`, `seamless_backfill_wait_ms`, `backfill_completion_ratio` 등을 대시보드에 노출합니다.
   - 구조화 로그(예: `seamless.backfill.attempt`, `seamless.sla.downgrade`)를 로그 파이프라인에 수집해 백필 및 SLA 위반을 추적합니다.【F:qmtl/docs/architecture/seamless_data_provider_v2.md†L82-L123】【F:qmtl/qmtl/runtime/io/seamless_provider.py†L139-L206】

6. **검증 및 회귀 테스트 실행**
   ```bash
   uv run -m pytest -W error -n auto \
     tests/qmtl/runtime/sdk/test_history_coverage_property.py \
     tests/qmtl/runtime/sdk/test_seamless_provider.py
   ```
   테스트 스위트는 커버리지 연산과 실패 주입 시나리오를 포함해 SDP 구성의 안정성을 검증합니다.【F:qmtl/docs/architecture/seamless_data_provider_v2.md†L124-L139】

## 3. 복잡도 평가

- **구성 요소 다양성**: 저장소, 페치, 백필, 라이브, 정합성, SLA 등 다수의 컴포넌트를 조정해야 하므로 초기 학습 곡선이 높습니다. 특히 분산 코디네이터와 지문(artifact fingerprint) 설정은 `qmtl.yml`의 `seamless` 섹션을 통해 세밀한 제어가 필요합니다.【F:qmtl/docs/architecture/seamless_data_provider_v2.md†L38-L123】【F:qmtl/qmtl/runtime/sdk/seamless_data_provider.py†L320-L373】
- **관측 의존도**: SLA 및 백필 상태를 모니터링하지 않으면 문제를 조기에 탐지하기 어렵습니다. Prometheus 및 Jsonnet 대시보드 구성은 운영팀 역량을 요구합니다.【F:qmtl/docs/architecture/seamless_data_provider_v2.md†L82-L123】
- **테스트 요구 사항**: 공식 테스트 스위트 실행이 권장되므로 CI 통합이나 로컬 환경에서 `uv` 기반 파이프라인을 유지해야 합니다.【F:qmtl/docs/architecture/seamless_data_provider_v2.md†L124-L139】

전체적으로 **중간 이상의 복잡도**로 평가할 수 있습니다. 인프라(코디네이터, 모니터링)와 애플리케이션 코드(전략, SLA, 정합성) 양측 설정이 필요하기 때문입니다.

## 4. 사용성 개선 제안

1. **구성 템플릿 제공** – `operations` 디렉터리에 YAML 기반 구성 샘플과 SLA/정합성 프리셋을 포함한 Compose 파일을 추가해 초기 설정을 단순화합니다.
2. **자동 검증 스크립트** – `scripts/` 아래에 환경 변수를 검사하고 코디네이터 연결성, Prometheus 지표 노출 여부를 확인하는 건강 검진 스크립트를 제공하면 배포 안정성을 높일 수 있습니다.
3. **모듈형 설정 객체** – `EnhancedQuestDBProvider` 초기화 인자 수를 줄이기 위해 설정 dataclass를 도입하고, 전략/SLA/지문 정책을 한 곳에서 선언하도록 개선하면 코드 가독성이 향상됩니다.【F:qmtl/qmtl/runtime/io/seamless_provider.py†L1-L213】
4. **대시보드 패키징** – Jsonnet 번들을 Helm Chart 또는 Terraform 모듈로 패키징해 Prometheus/Grafana 구성이 자동화되도록 하면 운영 복잡도를 줄일 수 있습니다.【F:qmtl/operations/monitoring/seamless_v2.jsonnet†L1-L123】

위 개선안을 적용하면 초기 설정 시간을 단축하고 운영 중 발생할 수 있는 오류를 더 쉽게 탐지할 수 있습니다.

## 5. 개선안 적용 작업 목록

1. **구성 템플릿 제공**
   - `operations/` 아래에 Seamless 구성용 새 하위 디렉터리를 만들고 예시 YAML 설정, SLA/정합성 프리셋, Compose 스택을 정의합니다.
   - 템플릿에서 사용되는 서비스/변수 정의를 README로 문서화하고, `mkdocs.yml` 내 운영 가이드 네비게이션을 업데이트합니다.

2. **자동 검증 스크립트 작성**
   - `scripts/` 디렉터리에 환경 변수 확인, 코디네이터 헬스 체크, Prometheus 지표 존재 여부를 점검하는 CLI 스크립트를 추가합니다.
   - 스크립트 실행 예시와 의존성을 문서화하고, CI 파이프라인에 선택적 건강 검증 단계를 배치합니다.

3. **모듈형 설정 객체 도입**
   - `EnhancedQuestDBProvider` 초기화 인자를 캡슐화하는 dataclass 또는 설정 객체를 설계하고, 기존 호출부의 마이그레이션 계획을 수립합니다.
   - 설정 객체에 전략, SLA, 정합성, 지문 정책 필드를 정의하고 관련 테스트 케이스를 추가합니다.

4. **대시보드 패키징 자동화**
   - `operations/monitoring/`의 Jsonnet 번들을 Helm Chart 또는 Terraform 모듈로 변환하는 패키징 파이프라인을 마련합니다.
   - 배포 자동화를 위해 샘플 values/variables 파일을 제공하고, Grafana/Prometheus 연동 절차를 운영 문서에 반영합니다.
