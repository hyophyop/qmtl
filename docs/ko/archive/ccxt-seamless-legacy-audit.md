---
title: "CCXT × Seamless 레거시 감사"
tags: [archive, ccxt, seamless]
author: "QMTL Team"
last_modified: 2025-08-21
---

# CCXT × Seamless 레거시 감사

## 요약
이 인벤토리는 레거시 CCXT × Seamless 설계 노트에 남아 있는 내용을 분류하여
[#1162](https://github.com/hyophyop/qmtl/issues/1162)에서 추적되는 마이그레이션을 지원합니다.
감사는 각 문서를 통합 청사진인 [`ccxt-seamless-integrated.md`](../architecture/ccxt-seamless-integrated.md)와 비교하고,
여전히 폐기된 파일을 가리키는 외부 링크를 강조합니다. 레거시 초안이 저장소에서 제거됨에 따라,
아래 표는 어떤 내용이 어디로 병합되었는지에 대한 역사적 기록으로 남습니다.

## 원문서별 남은 콘텐츠
아래 표는 통합 사양에 해당 항목이 없는 섹션, 다이어그램, 코드 샘플을 나열합니다.
각 행에는 마이그레이션 가이드가 포함되어 있어, 콘텐츠가 이관되면 레거시 파일을 은퇴시킬 수 있습니다.

### `ccxt-seamless-gpt5high.md`

| 레거시 섹션 | 마이그레이션 상태 | 비고 |
| --- | --- | --- |
| **Data Model** (`ts, open, high, low, close, volume` schema + interval semantics) | ✅ Migrated | Documented under “Data Model & Interval Semantics” in `ccxt-seamless-integrated.md`. |
| **Control Planes → Rate Limiting** (Redis/process split description) | ✅ Migrated | Expanded rate-limiter reference table and environment variable guidance now live in the integrated doc. |
| **Configuration & Recipes** (Python example using `EnhancedQuestDBProvider`) | ✅ Migrated | Example provider wiring added to the Data Plane section of the integrated blueprint. |
| **Operational Guidance** (env vars, metrics, monitoring references) | ✅ Migrated | Operational Practices now enumerate coordinator and Redis env vars plus enriched metrics. |
| **Testing** (mark `slow`, prefer recorded responses) | ✅ Migrated | Implementation and Testing Guidance sections call out pytest preflight, recorded fixtures, and `slow` marks. |
| **Extensions** (future ccxt.pro live feed, synthetic series, trades→bars repair) | ✅ Migrated | Captured in the new “Extensions” section appended to the integrated document. |

### `ccxt-seamless-gpt5codex.md`

| 레거시 주제 | 마이그레이션 상태 | 비고 |
| --- | --- | --- |
| **Feature Artifact Plane guardrails** (dataset_fingerprint-as_of discipline preventing domain bleed) | ✅ Migrated | Integrated doc now details read-only sharing, provenance, and the reproducibility contract under "Feature Artifact Plane". |
| **CCXT worker metadata workflow** (computing dataset_fingerprint/as_of at snapshot time) | ✅ Migrated | Publication workflow pseudo-code specifies when workers conform, fingerprint, and publish manifests. |
| **Artifact storage policy** (versioned retention in Feature Artifact store) | ✅ Migrated | Storage policy section clarifies hot vs cold roles, versioning, and watermark promotion. |
| **Observability metrics** (`backfill_completion_ratio` alongside SLA counters) | ✅ Migrated | Operational Practices → Metrics Catalog lists SLA timers, backfill ratios, and gating counters with alert guidance. |
| **Implementation roadmap** (connector packaging, Seamless adapter layer, persistence, domain gating, observability) | ✅ Migrated | Migration Path and Validation Benchmarks outline the phased rollout and acceptance criteria. |

### `ccxt-seamless-hybrid.md`

| 레거시 요소 | 마이그레이션 상태 | 비고 |
| --- | --- | --- |
| **Comprehensive configuration schema** (retry tuning, metrics catalog, partitioning, fingerprint options) | ✅ Migrated | Configuration blueprint now includes retry knobs, observability thresholds, and artifact partition templates. |
| **Reference implementation snippets** (`conform_frame`, `compute_fingerprint`, `maybe_publish_artifact`, domain gating helper) | ✅ Migrated | Publication workflow pseudo-code replaces the hybrid draft’s snippets. |
| **Operations & observability checklist** (metric names, alert thresholds, env vars) | ✅ Migrated | Operational Practices enumerate metrics, alerts, and environment variables, consolidating the hybrid guidance. |
| **Storage strategy (Hot vs. Cold) and stabilization workflow** | ✅ Migrated | Dedicated storage strategy section documents QuestDB vs artifact responsibilities and promotion sequencing. |
| **Migration pathway & acceptance criteria** | ✅ Migrated | Migration Path and Validation Benchmarks capture the seven-step rollout and readiness checks. |

## 레거시 문서에 의존하는 외부 링크
- ✅ `mkdocs.yml` 내비게이션은 이제 통합 청사진으로 직접 이동합니다(GPT5-High 항목 제거).
- ✅ [`ccxt-seamless-integrated.md`](../architecture/ccxt-seamless-integrated.md)는 기존 GPT5-High 자료를 인라인으로 포함하며 더 이상 보관 파일을 참조하지 않습니다.
- 과거의 `ccxt-seamless-hybrid.md` 참조는 트리에서 제거되었습니다. 앞으로는 통합 청사진으로 직접 연결하세요.

## 권장 후속 작업
1. 향후 업데이트 시에도 통합 청사진이 단일 SSOT로 남도록 확인하고, 분리된 서술 재도입을 피하세요.
2. 내비게이션 항목은 통합 문서를 가리키도록 유지하고, 새 링크가 생기면 보관 파일에 대한 잔여 참조를 제거하세요.
3. 향후 후속 작업을 위해 통합 상태를 요약한 마이그레이션 노트를 [#1162](https://github.com/hyophyop/qmtl/issues/1162)에 남기세요(Fixes #1163).
