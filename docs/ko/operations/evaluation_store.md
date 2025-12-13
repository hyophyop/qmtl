# Evaluation Store 운영 가이드

WorldService의 Evaluation Store는 `EvaluationRun`과 그 변경 이력을 **불변(append-only) 스토어**로 취급해, 검증 결과/오버라이드/정책 버전 추적을 운영·감사 가능하게 만드는 것을 목표로 합니다.

## 저장 모델 (요약)

- **키**: `(world_id, strategy_id, run_id)`
- **현재 스냅샷**: `evaluation_runs` (최신 상태 1건)
- **불변 이력**: `evaluation_run_history` (업데이트마다 revision append)
  - override 적용, extended validation 결과 반영 등 **모든 갱신은 history에 누적**됩니다.

## 불변성 원칙

- 동일 `(world_id, strategy_id, run_id)`에 대해 **과거 평가 결과를 덮어쓰지 않습니다.**
  - 최신 스냅샷은 업데이트될 수 있지만, 모든 변경은 `evaluation_run_history`에 append-only로 남습니다.
- 재평가가 필요하면 **새 `run_id`** 를 생성합니다.
- 운영/감사 목적상, `override_status=approved` 변경은 반드시 사유/승인자/타임스탬프를 포함해야 합니다.

## API 계약 (조회/이력/오버라이드)

대표 엔드포인트:

- 조회: `GET /worlds/{world_id}/strategies/{strategy_id}/runs`
- 단건: `GET /worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}`
- 이력: `GET /worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/history`
- 오버라이드: `POST /worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/override`
- 인바리언트 리포트: `GET /worlds/{world_id}/validations/invariants`

호환성 원칙:

- 필드 추가는 **additive** 로만 진행합니다(기존 필드 의미 변경/삭제 금지).
- `metrics`는 `returns/sample/risk/robustness/diagnostics` 블록을 기본으로 하며,
  모르는 필드는 무시(또는 `diagnostics.extra_metrics`로 보존)할 수 있어야 합니다.
- 대형 payload(예: covariance, realized returns, stress 결과)는 **offload(ref)** 를 우선 고려합니다.

## 보존(Retention) 정책 (권장)

운영 기준(권장 기본값):

- `evaluation_runs`: 최신 스냅샷은 운영 편의상 장기 보존(월드 삭제 시 함께 삭제)
- `evaluation_run_history`: 최소 **180일** 보존(감사/회귀 요구가 크면 1년까지 상향)

정리(Purge) 가이드:

- 용량/PII/규정 요구에 따라, 보존 기간이 지난 history 레코드만 정리합니다.
- 정리 작업은 **append-only 불변성(감사 가능성)** 을 훼손할 수 있으므로, 운영 승인을 거쳐 수행합니다.

### Retention 잡(코드/운영) 고정

- 스크립트: `scripts/purge_evaluation_run_history.py`
  - dry-run(기본): `WORLDS_DB_DSN=... WORLDS_REDIS_DSN=... uv run python scripts/purge_evaluation_run_history.py --retention-days 180`
  - 실행: `WORLDS_DB_DSN=... WORLDS_REDIS_DSN=... uv run python scripts/purge_evaluation_run_history.py --retention-days 180 --execute --output purge_report.json`
- GitHub Actions(스케줄/수동): `.github/workflows/evaluation-store-retention.yml`
  - `WORLDS_DB_DSN`, `WORLDS_REDIS_DSN` 시크릿이 설정된 경우에만 실행됩니다(미설정 시 skip).

## 운영 절차 (예시)

- 회귀/감사:
  - 특정 run의 변경 경로는 `/history`로 revision 단위 조회
  - 정책 변경 영향 평가는 (A) 샘플 세트 기반 `scripts/policy_diff_batch.py` + (B) 스토어 히스토리 기반 `scripts/policy_diff_store_history.py`로 증빙
- 오버라이드:
  - 승인(approved)은 사유/승인자/타임스탬프를 포함해야 하며,
    추후 재검토를 위해 관련 run의 `/history`를 함께 보관합니다.
