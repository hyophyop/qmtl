---
title: "Risk Signal Hub Runbook"
tags: [operations, risk, snapshots]
last_modified: 2025-12-10
status: draft
---

# Risk Signal Hub Runbook

## 1. Topology
- **WorldService**: `risk_hub` router (Bearer-protected), Redis cache, Postgres `risk_snapshots`, ControlBus consumer (CloudEvents type `risk_snapshot_updated`), activation updates push snapshots.
- **Gateway**: pushes after rebalance/fills/position sync with retry/backoff; large covariance/returns offloaded to blob-store (S3/Redis/file) and referenced via `covariance_ref`.
- **Blob store**: dev=file(`JsonBlobStore`), prod=S3 (option: Redis).
- **Events**: published on ControlBus/Kafka topic (`worldservice.server.controlbus_topic`) as CloudEvents with type `risk_snapshot_updated`; WS consumes to trigger ExtendedValidation/stress/live workers.
- **Headers**: `Authorization: Bearer <token>` (prod), `X-Actor` required, `X-Stage` (backtest/paper/live) strongly recommended for dedupe/alert labels.

## 2. Deployment checklist
- WS:
  - Configure `worldservice.server.controlbus_brokers/controlbus_topic`.
  - Redis DSN required (activation cache + hub cache).
  - Provide hub token (`risk_hub_token`) and share only with Gateway.
  - Blob store: dev `JsonBlobStore`; prod S3 bucket/prefix.
- Gateway:
  - `RiskHubClient` with token/retries/backoff/inline_cov_threshold.
  - Offload large covariance/returns to blob-store with shared ref schema.
  - Enable hub push after rebalance/fills/position sync.
- ControlBus/Queue:
  - Create Kafka topic `${controlbus_topic}` (route by CloudEvents `type`), size/retention checked.
  - WS consumer group `worldservice-risk-hub` alive.

## 3. Monitoring / alerts
- Freshness: latest snapshot `as_of` lag (warn ~10m, crit ~30m).
  - Script: `python scripts/risk_hub_monitor.py --base-url ... --world ... --warn-seconds 600`
- Duplicate/TTL: watch `risk_hub_snapshot_dedupe_total{world_id,stage}` and `risk_hub_snapshot_expired_total{world_id,stage}` spikes → validate producer headers/TTL.
- Producer validation: ensure gateway/risk-engine producers set `X-Actor`/`X-Stage` and enforce weights sum≈1, positive TTL, and hash before publishing.
- Events: ControlBus consumer errors/lag, retry rate.
- Blob-store: S3 4xx/5xx, Redis miss ratio.
- Hub HTTP: 401/5xx bursts.

## 4. Incident response
- Snapshot lag: check Gateway push retries, ControlBus lag; apply conservative fallback (corr/σ) if needed.
- Data corruption: re-download/refetch refs, re-emit on hash mismatch.
- Kafka outage: temporarily run with HTTP push only, resume consumer after lag catch-up.
- Producer violations: if weights/TTL/header are missing, inspect producer logs/metrics first and cross-check stage-specific dedupe/expired spikes on dashboards.

## 5. Handy commands
- Freshness (one-off):  
  `python scripts/risk_hub_monitor.py --base-url $WS_URL --world w1 --world w2 --token $HUB_TOKEN`
- Backfill:  
  `python scripts/backfill_risk_snapshots.py --dsn $DB --redis $REDIS --world w1`

### Producer rehearsal (publishing snapshots)

You can rehearse a producer path (e.g., gateway/risk engine) that publishes snapshots containing **realized returns / stress** to the WS hub under the same contract used in production.

- Sample payload: `operations/risk_hub/samples/risk_snapshot_with_realized_and_stress.json`
- Publisher script:
  - `uv run python scripts/publish_risk_hub_snapshot.py --base-url $WS_URL --world <world_id> --snapshot operations/risk_hub/samples/risk_snapshot_with_realized_and_stress.json --token $HUB_TOKEN --actor gateway --stage paper`

`scripts/publish_risk_hub_snapshot.py` validates the shared contract (`qmtl/services/risk_hub_contract.py`) for **weights sum≈1, ttl_sec>0, actor/stage, and hash consistency**, and offloads large payloads to a blob-store when needed (producing refs like `realized_returns_ref`, `stress_ref`, and `covariance_ref`).

## 6. Tests / validation
- Unit: `tests/qmtl/services/worldservice/test_risk_hub_*`, `test_risk_snapshot_publisher.py`.
- E2E (recommended): gateway→hub→ControlBus→WS worker, include large covariance ref and TTL-expired/delayed cases.
- Load: multi-world/strategy latest-hit ratio, ControlBus consumer lag.

## 7. Security
- Hub router: Bearer token required; network ACL limited to Gateway/infra subnets.
- Blob store: S3 IAM least privilege; Redis namespace/prefix (`risk-blobs:`); rotate tokens/keys.
