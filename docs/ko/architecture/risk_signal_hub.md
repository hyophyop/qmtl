---
title: "Risk Signal Hub — 포트폴리오/리스크 스냅샷 SSOT"
tags: [architecture, risk, hub, world]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# Risk Signal Hub — 포트폴리오/리스크 스냅샷 SSOT

!!! abstract "역할"
    Gateway가 생성하는 포트폴리오/리스크 스냅샷(weights, covariance_ref/행렬, stress, realized returns)을 수집·표준화해 **단일 진실 소스(SSOT)**로 보관한다.  
    WorldService·Exit Engine·모니터링은 허브의 API/이벤트만 소비해 Var/ES·stress·exit 신호를 계산하고, 스냅샷 신선도/결측 여부를 모니터링한다.

관련 문서:
- [Gateway](gateway.md)
- [WorldService](worldservice.md)
- 아카이브(초기 설계): [archive/risk_signal_hub.md](../archive/risk_signal_hub.md)
- 검증 아키텍처(icebox, 참고용): [design/world_validation_architecture.md](../design/icebox/world_validation_architecture.md)
- 운영 런북: [operations/risk_signal_hub_runbook.md](../operations/risk_signal_hub_runbook.md)

---

## 1. 시스템 경계와 데이터 흐름

```mermaid
flowchart LR
    GW[Gateway\n(rebalance/fill producers)] -->|HTTP POST /risk-hub| HUB[(Risk Signal Hub\nWS 라우터 + Storage)]
    HUB -->|risk_snapshot_updated\nControlBus event| WS[WorldService\n(ExtendedValidation / Stress / Live workers)]
    HUB --> EXIT[Exit Engine\n(향후)]
    HUB --> MON[Monitoring/Dashboards]
```

- **생산자**: Gateway 리밸런스/체결 경로가 스냅샷을 Hub에 POST, 필요 시 큰 공분산은 ref로 offload.
- **소비자**: WS ExtendedValidation/스트레스/라이브 워커가 Hub 조회/이벤트를 통해 Var/ES·stress 계산. Exit 엔진은 Hub 이벤트만 구독해 별도 exit 신호를 낼 수 있다.
- **이벤트**: ControlBus에 `risk_snapshot_updated` 이벤트를 발행해 워커/모니터링이 구독하도록 한다.

---

## 2. 런타임과 배포 경계

- Risk Signal Hub의 dev/prod 저장소 프로필, 토큰, blob offload, freshness 점검은 [Risk Signal Hub 운영 런북](../operations/risk_signal_hub_runbook.md)에서 운영 규칙으로 관리한다.
- 이 문서에서는 허브가 어떤 데이터를 표준화하고 어떤 서비스가 읽고 쓰는지만 규범적으로 정의한다.

---

## 3. 데이터 계약 (요약)

- 필수: `world_id`, `as_of`(ISO), `version`, `weights`(합≈1.0)
- 선택: `covariance`(작을 때 inline) 또는 `covariance_ref`, `realized_returns` 또는 `realized_returns_ref`, `stress`, `constraints`, `ttl_sec`, `provenance`, `hash`
- 검증: 가중치 합>0 및 1.0±1e-3, `as_of` ISO, TTL 만료시 캐시/조회에서 제외

### 3.1 v1 계약

- `X-Actor`/`X-Stage` 헤더는 필수이며, `provenance.actor/stage`로 저장된다.
- TTL 기본값: `ttl_sec=900`(15m). 상한: `ttl_sec <= 86400`(초과 시 422).
- 버전 충돌: `(world_id, version)` 충돌은 덮어쓰기 금지, **409(거절)** 로 수렴한다.
  - 동일 페이로드(동일 `hash`)의 재전송은 멱등 성공으로 처리하고 `risk_hub_snapshot_dedupe_total`로 계수한다.
- API:
  - `POST /risk-hub/worlds/{world_id}/snapshots` (write, token/헤더 필요)
  - `GET /risk-hub/worlds/{world_id}/snapshots/latest[?stage=...&actor=...&expand=true]`
    - `stage`/`actor`: `provenance.stage`/`provenance.actor`로 필터링한 최신 스냅샷을 반환한다.
    - `expand=true`: `covariance_ref`/`realized_returns_ref`/`stress_ref`를 가능한 경우 해석해 inline 필드(`covariance`, `realized_returns`, `stress`)를 함께 반환한다.
  - `GET /risk-hub/worlds/{world_id}/snapshots[?limit=...&stage=...&actor=...&expand=true]` (list)
  - `GET /risk-hub/worlds/{world_id}/snapshots/lookup?version=...|as_of=...`

### 3.2 `realized_returns` 계약 (v1, 저장 전용)

`realized_returns`는 “실현 수익률 시계열”을 스냅샷에 **저장**하기 위한 필드다. Hub는 `realized_returns`를 **계산/집계하지 않고**, 프로듀서(Gateway 등)가 계산한 결과를 저장한다.

- 권장 shape(전략별):
  - `realized_returns: { "<strategy_id>": [r1, r2, ...], ... }`
- 값 제약:
  - 각 원소는 **유한(finite) float** 이어야 한다. (`NaN/±Inf` 금지)
  - 빈 시계열은 허용하지 않는다. (최소 1개 이상)
- 순서/의미:
  - 배열의 순서는 “시간 순서(오래된 → 최신)”로 해석한다.
  - 리턴의 단위/주기(일간/바 단위 등), 비용 반영 여부(net/gross) 같은 의미론은 **프로듀서 계약**이며, `provenance` 또는 운영 문서로 고정한다.
- 크기/전송:
  - 큰 페이로드는 `realized_returns_ref`로 offload 하고, 조회 시 `expand=true`로 inline 데이터를 요청한다.

---

## 4. 저장·캐시 계층

- **메타/버전**: Postgres/SQLite(`risk_snapshots`)에 `(world_id, as_of/version)` 인덱스.
- **캐시**: Redis(또는 dev의 fakeredis)로 최신 스냅샷 hot path.
- **Blob offload**: prod에서만 Redis/S3; dev는 비활성. inline 기준 `inline_cov_threshold`를 Gateway/WS가 공유.

---

## 5. 운영 연계

- 인증, 토큰 공유, freshness 경보, worker 운영 절차는 [Risk Signal Hub 운영 런북](../operations/risk_signal_hub_runbook.md)에서 다룬다.
- 전역 대시보드/알림 라우팅은 [모니터링 및 알림](../operations/monitoring.md)과 [World Validation 운영 가시성](../operations/world_validation_observability.md)에서 본다.

---

## 6. 향후 확장

- Exit Engine: Hub 이벤트만으로 추가 exit 신호를 생성/발행.
- Stress/라이브 재시뮬레이션: Hub 이벤트→큐/ControlBus 워커로 스케줄링.
- 대용량 리턴/공분산 ref 표준화 및 보존 정책(Prod 전용) 세분화.

{{ nav_links() }}
