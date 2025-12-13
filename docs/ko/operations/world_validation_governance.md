# World Validation 거버넌스 (Override 재검토)

이 문서는 `world_validation_architecture.md` §12.3(Invariant 3)를 운영 관점에서 재현 가능하도록, **approved override 재검토 큐·기한·SLA**를 표준화합니다.

## 개념(요약)

- **Override(approved)**: 검증 결과(`summary.status`)가 `"pass"`가 아니더라도 운영/리스크 판단으로 예외를 승인한 상태.
- **Invariant 3**: approved override는 별도 목록으로 집계되고, 정해진 기간(예: 30/90일) 내 반드시 재검토되어야 합니다.

## 필수 기록 필드

approved override에는 아래 필드를 반드시 기록합니다.

- `override_reason`: 승인 사유
- `override_actor`: 승인자(주체)
- `override_timestamp`: 승인 시각(UTC ISO8601)

## 재검토 윈도우(기본값)

현재 코드 기준 기본 재검토 기한은 다음과 같습니다.

- `stage=live`: **30일**
- `risk_profile.tier=high` AND `client_critical=true`: **30일**
- 그 외: **90일**

## 큐 생성(운영 엔트리포인트)

- 스토리지 기반(권장):  
  `uv run python scripts/generate_override_rereview_report.py --output override_queue.md`
- GitHub Actions 스케줄(권장):  
  `.github/workflows/override-rereview-queue.yml` (secrets 미설정 시 자동 skip + 리포트 아티팩트 업로드)
- API 기반(월드별):  
  `GET /worlds/{world_id}/validations/invariants` → `approved_overrides` 확인

`approved_overrides` 항목에는 `review_due_at`, `review_overdue`, `missing_fields` 가 포함됩니다.

## 운영 절차(간단)

1) **매일/매주** 큐를 생성하고 `review_overdue=true` 또는 `missing_fields` 가 있는 항목을 우선 triage 합니다.  
2) 재검토 결과에 따라:
   - override 해제(정상화) 또는
   - override 갱신(사유/승인자/시각 갱신) 및 추가 조치 기록
3) 반복 발생 전략/월드는 원인 분석(룰/데이터/리밸런스/리스크 신호) 및 정책/룰 보강으로 연결합니다.

## Ex-post 실패 관리 (pass 후 실패율)

ex-post 실패는 “검증은 통과했지만, live 운영 관점에서 명백히 피했어야 할 실패”로 분류된 케이스를 의미합니다.

- 저장 위치(SSOT): `EvaluationRun.summary.ex_post_failures` (append-only 로그)
  - 필드: `case_id`, `status=candidate|confirmed`, `category`, `reason_code`, `severity`, `evidence_url`, `actor`, `recorded_at`, `source`, `notes`
  - taxonomy(예시):
    - `category`: `risk_breach`, `performance_failure`, `liquidity_failure`, `data_issue`, `ops_incident`
    - `severity`: `critical|high|medium|low`
- 기록 API:
  - `POST /worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/ex-post-failures`
  - 후보 자동 생성은 `status=candidate, source=auto`로 기록하고, 사람이 확정할 때 동일 `case_id`로 `status=confirmed, source=manual` 이벤트를 추가합니다.
- 리포트(월/분기 집계):
  - `uv run python scripts/generate_ex_post_failure_report.py --format md --output ex_post_failures.md`
  - GitHub Actions(스케줄/수동): `.github/workflows/ex-post-failure-report.yml` (secrets 미설정 시 skip)
