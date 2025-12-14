---
title: "Risk Signal Hub — 포트폴리오/리스크 스냅샷 SSOT"
tags: [architecture, risk, hub, world]
author: "QMTL Team"
last_modified: 2025-12-10
---

{{ nav_links() }}

# Risk Signal Hub — 포트폴리오/리스크 스냅샷 SSOT

!!! abstract "역할"
    Gateway가 생성하는 포트폴리오/리스크 스냅샷(weights, covariance_ref/행렬, stress, realized returns)을 수집·표준화해 **단일 진실 소스(SSOT)**로 보관한다.  
    WorldService·Exit Engine·모니터링은 허브의 API/이벤트만 소비해 Var/ES·stress·exit 신호를 계산하고, 스냅샷 신선도/결측 여부를 모니터링한다.

관련 문서:
- 아카이브(초기 설계): [archive/risk_signal_hub.md](../archive/risk_signal_hub.md)
- 검증 아키텍처: [design/world_validation_architecture.md](../design/world_validation_architecture.md)
- 운영 런북: [operations/risk_signal_hub_runbook.md](../operations/risk_signal_hub_runbook.md)

---

## 1. 시스템 경계와 데이터 흐름

```mermaid
flowchart LR
    GW[Gateway\n(rebalance/fill producers)] -->|HTTP POST /risk-hub| HUB[(Risk Signal Hub\nWS 라우터 + Storage)]
    HUB -->|PortfolioSnapshotUpdated\nControlBus event| WS[WorldService\n(ExtendedValidation / Stress / Live workers)]
    HUB --> EXIT[Exit Engine\n(향후)]
    HUB --> MON[Monitoring/Dashboards]
```

- **생산자**: Gateway 리밸런스/체결 경로가 스냅샷을 Hub에 POST, 필요 시 큰 공분산은 ref로 offload.
- **소비자**: WS ExtendedValidation/스트레스/라이브 워커가 Hub 조회/이벤트를 통해 Var/ES·stress 계산. Exit 엔진은 Hub 이벤트만 구독해 별도 exit 신호를 낼 수 있다.
- **이벤트**: `PortfolioSnapshotUpdated`를 ControlBus로 발행, 워커/모니터링이 구독해 후속 작업을 트리거.

---

## 2. 구성/배포 프로필

- **dev**: inline + fakeredis/인메모리 캐시만 사용(공분산 offload 비활성). 영속 스토리지(file/S3/Redis) 없이 “동작/검증”에 집중한 경량 경로.
- **prod**: Postgres `risk_snapshots` 테이블 + Redis 캐시, 필요 시 S3/Redis blob offload 활성화. ControlBus 이벤트 필수.
- `qmtl.yml` `risk_hub` 블록으로 Gateway(생산자)와 WS(소비자) 양쪽에 동일한 토큰/inline 기준/BlobStore 설정을 주입해 설정 드리프트를 방지한다.

---

## 3. 데이터 계약 (요약)

- 필수: `world_id`, `as_of`(ISO), `version`, `weights`(합≈1.0)
- 선택: `covariance`(작을 때 inline) 또는 `covariance_ref`, `realized_returns_ref`, `stress`, `constraints`, `ttl_sec`, `provenance`, `hash`
- 검증: 가중치 합>0 및 1.0±1e-3, `as_of` ISO, TTL 만료시 캐시/조회에서 제외

### 3.1 v1 계약(운영 기본값)

- `X-Actor`/`X-Stage` 헤더는 필수이며, `provenance.actor/stage`로 저장된다.
- TTL 기본값: `ttl_sec=900`(15m). 상한: `ttl_sec <= 86400`(초과 시 422).
- 버전 충돌: `(world_id, version)` 충돌은 덮어쓰기 금지, **409(거절)** 로 수렴한다.
  - 동일 페이로드(동일 `hash`)의 재전송은 멱등 성공으로 처리하고 `risk_hub_snapshot_dedupe_total`로 계수한다.
- API:
  - `POST /risk-hub/worlds/{world_id}/snapshots` (write, token/헤더 필요)
  - `GET /risk-hub/worlds/{world_id}/snapshots/latest`
  - `GET /risk-hub/worlds/{world_id}/snapshots` (list)
  - `GET /risk-hub/worlds/{world_id}/snapshots/lookup?version=...|as_of=...`

---

## 4. 저장·캐시 계층

- **메타/버전**: Postgres/SQLite(`risk_snapshots`)에 `(world_id, as_of/version)` 인덱스.
- **캐시**: Redis(또는 dev의 fakeredis)로 최신 스냅샷 hot path.
- **Blob offload**: prod에서만 Redis/S3; dev는 비활성. inline 기준 `inline_cov_threshold`를 Gateway/WS가 공유.

---

## 5. 보안/운영

- 인증: Hub 라우터 Bearer 토큰(`risk_hub.token`) — Gateway에만 공유.
- 가시성: `risk_hub_snapshot_lag_seconds`, `risk_hub_snapshot_missing_total` 메트릭 및 Alertmanager 룰(RiskHubSnapshotStale/Missing).
- 백그라운드 워커: ControlBus 소비자 예시 `scripts/risk_hub_worker.py`, 헬스 체크 `scripts/risk_hub_monitor.py`.

---

## 6. 향후 확장

- Exit Engine: Hub 이벤트만으로 추가 exit 신호를 생성/발행.
- Stress/라이브 재시뮬레이션: Hub 이벤트→큐/ControlBus 워커로 스케줄링.
- 대용량 리턴/공분산 ref 표준화 및 보존 정책(Prod 전용) 세분화.

{{ nav_links() }}
