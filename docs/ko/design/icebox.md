---
title: "Design Icebox 인덱스"
tags: [design, icebox, docs]
author: "QMTL Team"
last_modified: 2026-04-04
---

# Design Icebox 인덱스

이 페이지는 `docs/ko/design/icebox/` 아래의 참고용 초안과 스케치를 모아 보여주는 진입점이다.

- 목적: 현재 SSOT가 아닌 설계 초안을 한 곳에서 찾게 한다.
- 공개 범위: 개별 `icebox/*` 문서는 기본적으로 off-nav이며, 이 인덱스를 통해서만 탐색한다.
- 규범 여부: 아니다. 채택된 내용은 `docs/ko/architecture/`, `docs/ko/operations/`, 코드/테스트로 승격해야 한다.

## 사용 규칙

- 직접 구현 근거로 쓰기 전에 아키텍처 문서와 코드 상태를 함께 확인한다.
- 아직 ko/en 쌍이 없는 문서는 locale-incomplete draft로 간주하고 공식 nav에 올리지 않는다.
- 오래된 초안은 archive로 이동하거나 삭제한다.

## 문서 묶음

### World 검증 및 리스크

- [World 검증 계층 확장 설계 스케치](icebox/world_validation_architecture.md)
- [World 검증 v1 구현 계획](icebox/world_validation_v1_implementation_plan.md) - archived checklist
- [WorldService 평가 런 & 메트릭 API](icebox/worldservice_evaluation_runs_and_metrics_api.md)
- [QMTL 모델 리스크 관리(MRM) 프레임워크 스케치](icebox/model_risk_management_framework.md)
- [Exit Engine 개요 (초안)](icebox/exit_engine_overview.md)
- [World 전략 비중 조절(Weighting) v1.5 설계 초안](icebox/world_strategy_weighting_v1.5_design.md)

### 전략, UI, 구성 실험

- [QMTL UI](icebox/qmtl_ui.md)
- [전략/노드 자동 증류](icebox/strategy_distillation.md)
- [YAML-Only Configuration Overhaul](icebox/yaml_config_overhaul.md)
- [Seamless 데이터 물질화/검증 표면 분리 설계](icebox/seamless_materialize_jobs.md)

### 통합 및 스파이크 노트

- [QMTL SR(Strategy Recommendation) 통합 제안서](icebox/sr_integration_proposal.md)
- [SR-QMTL 데이터 일관성 설계 스케치](icebox/sr_data_consistency_sketch.md)
- [Operon 후속 통합 및 pyoperon 스파이크 노트](icebox/operon_followup_spike.md)

{{ nav_links() }}
