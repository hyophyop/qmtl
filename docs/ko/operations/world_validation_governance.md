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
- API 기반(월드별):  
  `GET /worlds/{world_id}/validations/invariants` → `approved_overrides` 확인

`approved_overrides` 항목에는 `review_due_at`, `review_overdue`, `missing_fields` 가 포함됩니다.

## 운영 절차(간단)

1) **매일/매주** 큐를 생성하고 `review_overdue=true` 또는 `missing_fields` 가 있는 항목을 우선 triage 합니다.  
2) 재검토 결과에 따라:
   - override 해제(정상화) 또는
   - override 갱신(사유/승인자/시각 갱신) 및 추가 조치 기록
3) 반복 발생 전략/월드는 원인 분석(룰/데이터/리밸런스/리스크 신호) 및 정책/룰 보강으로 연결합니다.

