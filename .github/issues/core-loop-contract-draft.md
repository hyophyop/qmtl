---
title: "[Core Loop] <요약을 적어주세요>"
labels: ["core-loop", "draft", "contract"]
assignees: []
---

## Goal / Scope / Out-of-scope
- Goal: 왜 이 작업이 필요한지, 기대 결과는 무엇인지 적습니다.
- Scope: 이번 이슈에서 해결할 구체 항목.
- Out-of-scope: 이번 이슈에서 다루지 않을 것.

## Draft spec pointer (single source of truth)
- ko source: 관련 설계/스펙 단일 출처 링크 (예: `docs/ko/design/core_loop_roadmap.md#...`).
- en mirror: 동일 위치의 영문 미러 링크.
- Note: 스펙 본문은 문서에만 두고, 이슈에는 링크만 남깁니다. 상태는 `draft — subject to change`.

## Open questions & decision owners
- [ ] 질문/불확실성 — 담당 결정자(@handle)
- [ ] ...

## Entry criteria (착수 전 확인)
- [ ] Draft spec v0.1 합의(주석: 변경 가능 상태) 완료.
- [ ] 계약 테스트 스켈레톤 추가 (`tests/e2e/core_loop/*`): `@pytest.mark.contract`, `xfail(reason="spec draft")`로 표시.
- [ ] 영향 범위/리스크 가설 정리.

## Exit criteria (마무리 요건)
- [ ] 스펙 업데이트 & ko/en 동기화, 관련 링크 정리.
- [ ] 계약 테스트에서 `xfail` 제거 후 통과 확인.
- [ ] `uv run mkdocs build --strict` 통과.
- [ ] 마이그레이션/호환성/롤백 플랜 명시.
- [ ] CI/운영 후속(예: #1790 게이트 연동) 필요 시 체크.

## Migration / compat / rollback
- 변경에 따른 사용자/전략 영향, 호환성 경로, 롤백/플래그 전략을 적습니다.

## Follow-ups
- [ ] Core Loop 계약 스위트 케이스 ID 정리/추가 (#1789 연동).
- [ ] 관측/메트릭 훅 추가 필요 여부.
- [ ] 기타 후속 이슈 번호.
