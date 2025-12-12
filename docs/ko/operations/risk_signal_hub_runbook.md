---
title: "Risk Signal Hub 운영 런북"
tags: [operations, risk, snapshots]
author: "QMTL Team"
last_modified: 2025-12-10
status: draft
---

# Risk Signal Hub 운영 런북

## 1. 구성 요약
- **WS**: `risk_hub` 라우터(토큰 보호), Redis 캐시, Postgres `risk_snapshots` 테이블, ControlBus 이벤트 소비(`risk_snapshot_updated`), activation 변경 시 스냅샷 push.
- **Gateway**: 리밸런스/체결 후 hub push(재시도/backoff), 대용량 공분산은 blob-store(S3/Redis/file)로 offload → `covariance_ref`.
- **Blob store**: dev=file(`JsonBlobStore`), prod=S3(+옵션: Redis).
- **이벤트**: ControlBus/Kafka 토픽 공통(`risk_snapshot_updated`); WS 소비 → ExtendedValidation/스트레스/라이브 워커 트리거.
  - 헤더 계약: `Authorization: Bearer <token>`(prod), `X-Actor`(필수), `X-Stage`(backtest/paper/live 등 — dedupe/알람 분리용).

## 2. 배포 체크리스트
- WS:
  - `worldservice.server.controlbus_brokers/controlbus_topic` 설정.
  - Redis DSN 필수(activation cache + hub 캐시).
  - Hub 토큰(`risk_hub_token`) 주입, gateway에만 공유.
  - Blob store: dev는 `JsonBlobStore`, prod는 S3 bucket/prefix 지정.
- Gateway:
  - `RiskHubClient`에 토큰/재시도/backoff/inline_cov_threshold 설정.
  - Offload 대상 공분산/returns를 blob-store 업로드(동일 ref 스키마).
  - 리밸런스·체결·포지션 싱크 후 hub push 경로 활성화.
- ControlBus/Queue:
  - Kafka 토픽 `risk_snapshot_updated` 생성, 파티션/보존일 확인.
  - WS `RiskHubControlBusConsumer` 그룹 생성(`worldservice-risk-hub`).

## 3. 모니터링/알람
- Freshness: 최신 스냅샷 `as_of` 지연(예: 10m) 초과 시 WARNING, 30m 초과 CRITICAL.
  - 스크립트: `scripts/risk_hub_monitor.py --base-url ... --world ... --warn-seconds 600`.
- 중복/TTL: `risk_hub_snapshot_dedupe_total{world_id,stage}`·`risk_hub_snapshot_expired_total{world_id,stage}` 급증 시 프로듀서 헤더/TTL 규칙 점검.
- 프로듀서 밸리데이션: 게이트웨이/리스크 엔진 프로듀서가 `X-Actor`/`X-Stage` 헤더를 넣고, weights 합≈1·TTL>0·hash 설정이 선행되는지 확인.
- 이벤트 실패: ControlBus 소비 오류/지연 카운터, 재시도율.
- Blob-store 접근: S3 4xx/5xx, Redis miss율.
- Hub 라우터 401/5xx 급증 모니터링.

## 4. 장애 대응
- 스냅샷 지연: gateway push 재시도 확인, ControlBus lag 확인 → 임시 fallback(보수적 상관/σ) 적용.
- 데이터 손상: ref 재다운로드/재생성, hash 불일치 시 재발행.
- Kafka 장애: hub 라우터 HTTP push만으로 임시 운영, lag 해소 후 소비 재개.
- 프로듀서 위반: weights 합/TTL/헤더 누락 시 producer 로그·메트릭을 우선 확인하고, 동일 스테이지의 dedupe/expired 급증 여부를 대시보드에서 교차 확인.

## 5. 운영 명령 모음
- Freshness 체크(once):  
  `python scripts/risk_hub_monitor.py --base-url $WS_URL --world w1 --world w2 --token $HUB_TOKEN`
- Backfill:  
  `python scripts/backfill_risk_snapshots.py --dsn $DB --redis $REDIS --world w1`

## 6. 테스트/검증
- 단위: `tests/qmtl/services/worldservice/test_risk_hub_*`, `test_risk_snapshot_publisher.py`.
- e2e(추천): gateway→hub→ControlBus→WS worker 경로, 큰 공분산 ref 포함, TTL 만료/지연 시나리오.
- 부하: 다수 world/전략 기준 latest 조회 hit율, ControlBus 소비 lag.

## 7. 보안
- Hub 라우터: Bearer 토큰 필수, 네트워크 ACL로 gateway/infra 서브넷만 허용.
- Blob store: S3 IAM 최소 권한, Redis 분리 네임스페이스/키 프리픽스(`risk-blobs:`), 토큰/키 rotation.
