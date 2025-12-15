---
title: "심리스 데이터 프로바이더 v2 아키텍처"
tags: [architecture, seamless, data]
author: "QMTL Team"
last_modified: 2025-12-15
---

{{ nav_links() }}

# 심리스 데이터 프로바이더 v2 아키텍처

## 0. 목적과 Core Loop 상 위치

- 목적: Seamless Data Provider(SDP) v2가 **데이터 정규화·적합성 검증·백필·SLA·관측 가능성**을 어떻게 조합해, 전략/월드에 일관된 히스토리/라이브 데이터를 제공하는지 아키텍처 수준에서 정의합니다.
- Core Loop 상 위치: Core Loop의 **“데이터 공급 자동화” + “시장 replay 백테스트”** 단계를 뒷받침하는 데이터 플레인 설계입니다. Runner.submit과 WorldService가 기대하는 데이터 품질/커버리지를 보장하는 책임을 집니다.

### 0‑A. Core Loop 정렬 요약

- SDP v2는 런타임에서 cache→storage→backfill→live 경로와 ConformancePipeline/SLA/metrics를 통해 데이터 품질을 관리한다.
- `world.data.presets[]`가 선언된 월드는 world/preset 정보를 기반으로 Runner/CLI가 **Seamless preset + data spec**만으로 SDP 인스턴스를 자동 구성해 `StreamInput`에 주입하며, 사용자는 data preset/fingerprint만 의식하면 된다.
- 본 문서는 데이터 플레인 관점에서 Core Loop 정렬을 규범화하고, [rewrite_architecture_docs.md](../archive/rewrite_architecture_docs.md)와 함께 “world 중심 데이터 preset → SDP wiring” 규약까지 포함하도록 확장한다.

> **상태:** 심리스 데이터 프로바이더 v2 아키텍처는 런타임에 정식 적용되었습니다. 분산 백필 코디네이터가 인프로세스 스텁을 대체했고, `SLAPolicy` 예산이 강제되며, 아래에서 언급하는 관측 지표가 기본으로 방출됩니다. Core Loop 골든 시그널 세트는 `../operations/core_loop_golden_signals.md`에 정리되었으며, 남은 로드맵은 스키마 거버넌스 유지·대시보드 확장 같은 점진 개선에 집중합니다.

심리스 데이터 프로바이더(SDP)는 초기 설계 문서에서 설명한 프로토타입을 넘어, 요청이 들어오는 순간부터 데이터 품질·백필 SLA·스키마 안전성을 보장하는 프로덕션 시스템으로 진화했습니다. 아래 절에서는 현재도 진행 중인 기능을 명시해 독자가 런타임이 제공하는 보증을 과대평가하지 않도록 합니다.

## 상위 흐름

```mermaid
graph TD
    Client[전략 / 노드] -->|읽기 요청| Gateway
    Gateway --> SDP
    subgraph Seamless Data Provider
        SDP --> ConformancePipeline
        ConformancePipeline --> Rollup[스키마/시간 롤업]
        Rollup --> Flags[품질 플래그 + 갭]
        Flags --> Reports[회귀 & 적합성 보고서]
        Reports --> BackfillTrigger
        BackfillTrigger --> Coordinator
        Coordinator --> Sources[스토리지 & 라이브 소스]
        Coordinator --> Metrics
        Metrics --> SLAEnforcer
        SLAEnforcer --> Observability[메트릭 / 트레이스 / 알림]
        SLAEnforcer --> Client
    end
    Coordinator --> SchemaRegistry
```

요청은 게이트웨이에 들어와 심리스 데이터 프로바이더에서 정규화된 후 적합성 파이프라인을 통과하고, 데이터가 반환되기 전에 각 단계가 명시적인 산출물(플래그, 보고서, 메트릭)을 방출해 하류 시스템이 응답의 완결성을 추론할 수 있도록 합니다.

## world preset → Seamless 매핑 규약

T3 P0‑M1에서 정의한 “world + data preset만으로 Seamless 자동 연결” 계약을 데이터 플레인 관점에서 고정한다. 월드 문서의 `data.presets[]` 스키마는 이 섹션에 정의된 Seamless preset 맵을 SSOT로 참조한다.

### 1) Seamless preset 맵(SSOT)

- 위치: 기본값은 패키지된 `qmtl/examples/seamless/presets.yaml`, 운영 환경에서는 `SeamlessConfig.presets_file`(환경 변수/CLI 구성에서 주입)로 교체 가능하다.
- 스키마(요약)

```yaml
version: 1
data_presets:
  ohlcv.binance.spot.1m:
    kind: "ohlcv"
    interval_ms: 60000
    storage: "questdb:ohlcv_binance_spot_1m"
    backfill:
      source: "ccxt:binance"
      mode: "background"
      window_bars: 1800
    live:
      feed: "binance.ws.kline.1m"
      max_lag_seconds: 45
    conformance_preset: "strict-blocking"
    sla_preset: "baseline"
    stabilization_bars: 2
```

- 필드 해석
  - `kind`: 데이터셋 유형(ohlcv/trades/orderbook 등)으로 conformance 스키마·노드 타입을 결정한다.
  - `interval_ms`: 요청 인터벌. world preset이 다른 값을 지정하면 오류로 간주한다.
  - `storage`/`backfill`/`live`: `SeamlessDataProvider`의 `storage_source`/`backfiller`/`live_feed`에 매핑된다. 소스 식별자는 커넥터 레지스트리에서 해석한다(예: `questdb:<table>`, `ccxt:<exchange>`, `binance.ws.<channel>`).
  - `conformance_preset`/`sla_preset`: `SeamlessConfig` 기본값을 오버라이드하며, world preset의 `seamless.*`가 있으면 그것이 다시 우선한다.
  - `stabilization_bars`: 라이브→스토리지 경계에서 버릴 바 수. world preset에 값이 있으면 합류 시 최소값으로 사용한다.

### 2) world → Seamless 바인딩 절차

1. Runner/CLI는 `world.data.presets[]`를 읽어 preset ID를 선택한다(명시하지 않으면 첫 항목).
2. 선택한 preset ID를 위의 `data_presets` 맵에서 찾는다. 없으면 즉시 실패(서킷).
3. world 필드와 Seamless preset을 병합해 `SeamlessDataProvider`를 생성한다.
   - `interval_ms` → `StreamInput.interval_ms` 및 Seamless `compute_missing_ranges` 입력.
   - `window.warmup_bars` → `BackfillConfig.window_bars`; `backfill_start`가 있으면 `BackfillConfig.start`.
   - `seamless.sla_preset`/`conformance_preset` → `SeamlessConfig`에 주입.
   - `live.max_lag` → `SeamlessDataProvider._domain_gate_evaluator` 지연 한도.
   - `universe`(symbols/tag query/venue/asset_class) → 데이터 소스 선택 및 conformance 스키마 선택에 사용.
   - `stabilization_bars` → Seamless `stabilization_bars`.
4. preset에 정의된 소스가 접근 불가하거나 스키마와 불일치하면 `ConformancePipelineError`/`SeamlessSLAExceeded`를 그대로 노출해 Runner가 compute-only로 강등하거나 중단하도록 한다.

### 3) 표준 preset 세트(월드 문서와 동일)

| preset ID | storage/backfill | live feed | default SLA/Conformance | note |
|---|---|---|---|---|
| `ohlcv.binance.spot.1m` | QuestDB `ohlcv_binance_spot_1m`, CCXT(Binance) backfill, `window_bars=1800` | Binance WS `kline@1m` (fallback: CCXT) | `sla_preset=baseline`, `conformance_preset=strict-blocking`, `interval_ms=60000`, `stabilization_bars=2` | Crypto 1m momentum/arb |
| `ohlcv.polygon.us_equity.1d` | QuestDB `ohlcv_us_equity_1d`, Polygon REST backfill, `window_bars=120` | none (EOD only) | `sla_preset=tolerant-partial`, `conformance_preset=strict-blocking`, `interval_ms=86400000`, `stabilization_bars=0` | US equity EOD factors |

- 계약 테스트/예제 훅(#1778/#1789): `tests/e2e/core_loop` 스택에서 world fixture가 첫 preset을 포함하고, Gateway/WS 스텁이 해당 preset ID를 반환하도록 구성해 Seamless 오토와이어링을 검증한다. preset 맵이 비어 있으면 테스트는 즉시 실패해야 한다.

## 적합성 파이프라인

`ConformancePipeline`은 세 단계로 동작합니다. 호출자는 여전히 명시적으로 `ConformancePipeline` 인스턴스를 넘겨 옵트인하지만, 런타임은 데이터 경로와 함께 구조화된 보고서를 방출합니다. 각 단계는 다음과 같습니다.

1. **스키마 롤업**은 표준 레지스트리 스키마를 기준으로 관측치를 집계하여 누락된 컬럼이나 잘못된 열거형이 클라이언트에 도달하기 전에 차단합니다.
2. **시간 롤업**은 심볼과 그레뉼러리티별 완전성 윈도우를 계산해 스토리지와 라이브 데이터를 정렬된 바 형태로 혼합할 수 있게 합니다.
3. **품질 플래그와 보고서**는 `qmtl://observability/seamless/<node>`에 게시되는 회귀 다이제스트를 생성하고 감사 목적에 맞춰 보관합니다.

2025년 9월 런타임 업데이트 이후 `EnhancedQuestDBProvider`를 통해 파이프라인이 기본 활성화됩니다. 정규화 경고는 반환된 보고서를 통해 계속 노출되며, 파이프라인에서 발생한 모든 경고 또는 플래그는 `ConformancePipelineError`를 발생시킵니다. 단, 공급자를 `partial_ok=True`로 인스턴스화하면 정규화된 프레임을 반환하고 `SeamlessDataProvider.last_conformance_report`를 통해 보고서를 제공해 레지스트리 롤아웃이 끝날 때까지 차단 동작을 지연할 수 있습니다.

## 분산 백필 코디네이터

`QMTL_SEAMLESS_COORDINATOR_URL`이 설정되면 분산 코디네이터가 기본값으로 사용됩니다. SDK는 `DistributedBackfillCoordinator`를 인스턴스화해 Raft 서비스와 리스를 협상합니다. **프로필별 가드:** prod 프로필에서는 URL 누락/헬스 체크 실패 시 인메모리 스텁으로 폴백하지 않고 초기화에 실패합니다(헬스 재시도 3회, 백오프 약 10초). dev 프로필에서는 경고를 남기고 인메모리 스텁으로 폴백할 수 있습니다. 프로덕션 구현은 다음 기능을 제공합니다.

- **정렬된 리스**를 통해 중복 요청이 동일 작업을 공유하도록 하여 백필 중복을 제거합니다.
- **리스 만료 텔레메트리**와 자동 실패 신호를 통해 작업 중단 시 정체된 클레임을 감지합니다.
- **부분 완료 추적**으로 `backfill_completion_ratio{node_id,interval,lease_key}` 게이지를 프로메테우스에 방출하고 `seamless.backfill` 구조화 로그를 기록합니다.
- **복구 훅**이 실패한 리스를 재처리 대상으로 표시해 모든 샤드가 완료되거나 명시적 위반을 보고하도록 보장합니다.

소비자는 더 이상 코디네이터 스텁을 제공할 필요가 없습니다. 환경 설정으로 서비스를 활성화하면 분산 경로가 작동합니다.

## SLA 집행

모든 심리스 요청에서 `SLAPolicy` 예산이 존중됩니다. 프로바이더는 스토리지, 백필, 라이브 피드, 전체 요청에 사용한 시간을 추적하고 `seamless_sla_deadline_seconds{node_id,phase}` 히스토그램에 기록합니다. 구성된 예산을 초과하면 런타임은 `SeamlessSLAExceeded`를 발생시키고 `seamless.sla`에 위반을 기록하며 호출자가 우아하게 강등할 수 있도록 실패를 노출합니다. 정책은 동기식 갭 바의 최대 개수도 제한할 수 있으며, 위반 시 동일한 예외를 `sync_gap` 단계로 발생시킵니다.

트레이싱 훅은 향후 스팬 정보를 풍부하게 할 준비가 되어 있고, 현재는 메트릭과 예외 동작이 활성화되어 있습니다.

## 스키마 레지스트리 거버넌스

Seamless v2는 이제 QMTL 공통 스키마 레지스트리 계층과 연동됩니다. 데이터 정규화·롤업에서 사용하는 스키마는
`qmtl.foundation.schema.SchemaRegistryClient`를 통해 관리되며, 구성에 따라 인메모리/원격 레지스트리를 선택합니다.

- 레지스트리 통합
  - 기본값은 인메모리 `SchemaRegistryClient`이며, 원격 사용 시 `connectors.schema_registry_url`
    또는 `QMTL_SCHEMA_REGISTRY_URL` 환경 변수를 통해 `RemoteSchemaRegistryClient`를 활성화합니다.
  - ConformancePipeline의 스키마 롤업 단계는 이 레지스트리에 저장된 **정규 스키마**를 기준으로 호환성을 판단하도록 설계되었습니다.
- 검증 모드
  - 거버넌스는 `validation_mode` 인자나 `QMTL_SCHEMA_VALIDATION_MODE` 환경 변수를 통해
    `canary` / `strict` 모드를 선택합니다(`canary` 기본, `strict` 강제).
  - **카나리(canary)** 모드는 요청을 미러링하고 호환성 진단을 기록하지만 응답을 차단하지 않습니다.
  - **스트릭트(strict)** 모드는 승인된 스키마와 호환되지 않는 페이로드가 감지되는 즉시 응답을 차단하고
    `SchemaValidationError`를 발생시킵니다.
- 관측·감사
  - 모든 호환성 위반은 Prometheus 카운터 `seamless_schema_validation_failures_total{subject,mode}`에 기록되며,
    대시보드는 이 메트릭을 기반으로 카나리→스트릭트 전환에서 회귀를 감시합니다.
  - 엄격 롤아웃은 `scripts/schema/audit_log.py`를 사용해 스키마 번들 SHA와 검증 윈도우를 감사 로그에 고정합니다.
    세부 수동은 `docs/ko/operations/schema_registry_governance.md` 런북에 정의되어 있습니다.

이로써 초기 설계에서 남아 있던 “best-effort 수준의 검증, 중앙 레지스트리 미사용, 감사/번들 지표 부재” 공백은 해소되었으며,
Seamless 데이터 플레인도 Core Loop 로드맵의 **P‑C / T3 P1‑M2 — 스키마 레지스트리 거버넌스 정식화** 기준에 맞춰 운영됩니다.

### 카나리 → 스트릭트 전환 체크리스트 (운영)

1. **스키마 등록**: SchemaRegistry에 새 subject/버전을 올리고 번들 SHA를 기록합니다.  
   `uv run python scripts/schema/audit_log.py --bundle schemas/vX --note "ohlcv 1m vX canary"`
2. **카나리 배포**: `validation_mode=canary`(또는 `QMTL_SCHEMA_VALIDATION_MODE=canary`)로 Seamless 인스턴스를 재기동합니다.  
   Runner/CLI는 world preset에 포함된 데이터 스펙을 subject로 사용하므로 별도 토글이 필요 없습니다.
3. **모니터링**: `seamless_schema_validation_failures_total{subject,mode="canary"}`와 ConformancePipeline 경고 로그를 24–48h 관찰합니다.
4. **스트릭트 전환**: `validation_mode=strict`로 승격 후 동일 메트릭/로그를 확인합니다. 실패 시 즉시 카나리로 되돌리고 대상 subject를 차단합니다.
5. **감사**: 전환 시점의 번들 SHA와 윈도우를 감사 로그에 추가하고 대시보드 메모를 남깁니다.
6. **롤백 경로**: strict에서 실패하는 subject는 `validation_mode=canary`로 즉시 다운그레이드하고, 문제 스키마를 잠시 tombstone 처리한 뒤 재배포합니다.

### 로드맵 매핑 (P‑C / T3 P1‑M2)

- #1150 — 레지스트리 계약·검증 모드·감사: `SchemaRegistryClient` / `RemoteSchemaRegistryClient`, `validation_mode`·`QMTL_SCHEMA_VALIDATION_MODE`, `QMTL_SCHEMA_REGISTRY_URL` 토글, `seamless_schema_validation_failures_total` 메트릭, `scripts/schema/audit_log.py` 워크플로우가 제공하는 범위를 의미합니다.
- #1151 — 관측·런북 자산: `operations/monitoring/seamless_v2.jsonnet` 대시보드, `alert_rules.yml`(SeamlessSla99thDegraded/SeamlessBackfillStuckLease/SeamlessConformanceFlagSpike), `scripts/seamless_health_check.py` 헬스체크가 함께 배포되어 있습니다. 핵심 메트릭은 `seamless_sla_deadline_seconds`, `backfill_completion_ratio`, `seamless_conformance_flag_total`입니다.
- #1152 — 검증/실패 주입 회귀: Hypothesis 커버리지·실패 주입·레지스트리 거버넌스 테스트(`tests/qmtl/runtime/sdk/test_history_coverage_property.py`, `tests/qmtl/runtime/sdk/test_seamless_provider.py`, `tests/qmtl/foundation/schema/test_registry.py`)는 아래 명령으로 실행되며 `.github/workflows/ci.yml` `test` 잡에서 동일하게 실행됩니다.

## 관측 지표

프로메테우스는 위에서 설명한 코디네이터 및 SLA 메트릭과 기존 적합성 카운터를 함께 노출합니다. 운영 가이드에서 언급한 Jsonnet 대시보드는 이 메트릭만으로 바로 렌더링할 수 있습니다. Core Loop 골든 시그널 대시보드는 이 데이터 플레인 뷰를 그대로 사용하며 SLO는 `../operations/core_loop_golden_signals.md`에 고정되어 있습니다. 스키마 레지스트리 작업이 완료되면 트레이싱 스팬 속성이 더욱 풍부해지겠지만, 코디네이터와 SLA 계측을 위해 추가 변경은 필요하지 않습니다.

## 검증 & 실패 주입 테스트 스위트

Seamless v2는 본 문서의 약속을 뒷받침하는 회귀 스위트를 제공합니다.

- **커버리지 대수 프로퍼티 테스트**는 `merge_coverage`와 `compute_missing_ranges`를 Hypothesis 기반 시나리오로 실행해 구간 경계와 누락 범위 계산이 결합법칙을 만족하며 손실이 없음을 보증합니다.
- **실패 주입 테스트**는 코디네이터 리스 손실, SLA 데드라인 초과, 스키마 불일치를 시뮬레이션해 런타임이 예상대로 `SeamlessSLAExceeded` 또는 `ConformancePipelineError`를 노출하는지 확인합니다.
- **관측 스냅샷**은 백필 동안 방출되는 프로메테우스 카운터와 구조화 로그 필드(`node_id`, `interval`, `start`, `end`)를 보호합니다.

다음 명령으로 로컬이나 CI에서 스위트를 실행할 수 있습니다.

```
uv run -m pytest -W error -n auto \
  tests/qmtl/runtime/sdk/test_history_coverage_property.py \
  tests/qmtl/runtime/sdk/test_seamless_provider.py \
  tests/qmtl/foundation/schema/test_registry.py
```

위 명령은 `.github/workflows/ci.yml` `test` 잡에서도 동일 경로로 실행됩니다.

## 다음 단계

이제 팀은 분산 코디네이터, SLA 집행, 스키마 레지스트리 거버넌스를 포함한 Seamless v2 스택을 활용해
프로덕션 워크로드를 운영할 수 있으며, 추가 런타임 릴리스를 기다릴 필요가 없습니다. 원래 남아 있던
스키마 거버넌스 이정표는 #1150–#1152 이슈를 통해 마무리되었고, 본 문서에서 설명하는 코디네이터·SLA·레지스트리 경로는
현재 구현 상태를 반영합니다.

향후 조정 사항(대시보드/런북 다듬기, Core Loop 로드맵와의 정합성 유지)은 Core Loop 로드맵의 P‑C / T3 항목과
`docs/ko/operations/schema_registry_governance.md` 런북을 기준으로 관리합니다.

{{ nav_links() }}
