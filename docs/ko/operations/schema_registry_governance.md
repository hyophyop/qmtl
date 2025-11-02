---
title: "스키마 레지스트리 거버넌스"
tags: [operations]
author: "QMTL Team"
last_modified: 2025-09-25
---

{{ nav_links() }}

# 스키마 레지스트리 거버넌스

이 런북은 QMTL에서 스키마와 정규화 규칙을 버전 관리하고 롤아웃하는 방식을 정의합니다.

목표
- 깨지는 스키마 변경이 눈치채지 못한 채 프로덕션에 반영되는 것을 방지
- 스키마 업데이트를 위한 명확한 승인 및 드라이런 경로 제공

워크플로
1) **작성**: 스키마 변경을 제안합니다(`docs/reference/schemas/*.json` 및 연관 코드/데이터 어댑터를 수정하는 PR).
2) **드라이런**: 샘플 데이터셋과 `SchemaRegistryClient` 를 전용 브랜치에서 검증합니다. 문서 참조 일관성을 확인하기 위해 `uv run mkdocs build` 를 실행하세요.
3) **승인**: 데이터 플랫폼 + 전략 오너의 이중 승인을 받고, PR 설명에 리뷰어 메모를 기록합니다.
4) **카나리**: 최소 48시간 동안 `validation_mode=canary` 로 배포합니다. `seamless_schema_validation_failures_total{subject,mode}` 와 리그레션 리포트를 추적하세요. 카나리 모드는 호환되지 않는 스키마도 게시하되 실패를 기록합니다.
5) **엄격 롤아웃**: 카나리가 통과한 후 `validation_mode=strict` 로 전환합니다. 엄격 모드는 호환되지 않는 스키마를 차단하고 필드 제거/변경 시 `SchemaValidationError` 를 발생시킵니다. 아래 감사 로그에 변경 참조, 타임스탬프, 검증 근거를 업데이트하세요.

도구
- `qmtl.foundation.schema.SchemaRegistryClient` — 기본은 인메모리이며, 원격 사용 시 `connectors.schema_registry_url` 또는 `QMTL_SCHEMA_REGISTRY_URL` 환경 변수를 설정합니다. 거버넌스는 `validation_mode` 또는 `QMTL_SCHEMA_VALIDATION_MODE` (`canary` 기본, `strict` 강제)를 통해 구성합니다.
- `scripts/check_design_drift.py` — 문서/코드 사양 드리프트를 감지합니다.
- `scripts/schema/audit_log.py` — 엄격 모드 승격을 기록하고 스키마 번들 SHA를 저장합니다.

검증은 구조화된 `SchemaValidationReport` 를 출력하고, 호환성 문제가 발견되면 Prometheus 카운터 `seamless_schema_validation_failures_total` 을 증가시킵니다. 카운터는 `subject`, `mode` 라벨을 포함해 대시보드가 엄격 모드 회귀에 경보를 발생시킬 수 있습니다.

엄격 롤아웃이 완료될 때 감사 헬퍼를 실행하세요.

```bash
uv run python scripts/schema/audit_log.py \
  --schema-bundle-sha "<bundle sha>" \
  --change-request "https://qmtl/changes/<id>" \
  --validation-window "48h canary" \
  --notes "no validation failures observed"
```

`--dry-run` 을 사용하면 리포지토리를 수정하지 않고 테이블 업데이트를 미리 볼 수 있습니다.

가드레일
- 항상 엄격 모드 이전에 카나리 검증을 진행하고 관찰 기간을 건너뛰지 마세요.
- `schema_compat_id` 변경 이력을 유지하고 호환성 경계가 바뀌면 아키텍처 사양을 업데이트하세요.
- 모든 엄격 모드 승격을 아래 표에 기록하세요. 누락된 항목은 이후 스키마 변경을 차단합니다.

## Strict Mode 감사 로그

| Date       | Schema Bundle SHA | Change Request | Validation Window | Notes |
|------------|------------------|----------------|-------------------|-------|
| _TBD_      |                  |                |                   |       |

{{ nav_links() }}
