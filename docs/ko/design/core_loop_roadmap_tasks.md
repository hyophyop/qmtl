# Core Loop 로드맵 태스크

괄호 안은 대표 이슈 번호입니다. Phase 2부터 착수합니다.

## Phase 0 – 기반 깔기 (spec/스켈레톤)
- Core Loop 계약 테스트 스켈레톤 먼저 생성: tests/e2e/core_loop 골격 (#1788).
- spec 성 이슈들부터 처리:
  - SubmitResult/WS 스키마 정렬 방향 잡기 (#1764, #1771).
  - world data preset 스펙 정의 (#1776).
  - NodeID/TagQuery 결정성 규칙 문서화 (#1782).
  - Determinism 체크리스트 항목 목록/범위 정리 (#1785).

## Phase 1 – ExecutionDomain/default-safe 수직 슬라이스(“모드/도메인 규약” 하나를 끝까지 밀기)
- WS 경계부터 고정: WS ExecutionDomain 검증/강등 (#1773).
- Runner/CLI 입력 검증 강화 (#1767) → SDK/CLI default-safe 강등 구현 (#1768).
- Runner 제출 힌트 제거 (WS effective_mode 우선) (#1774).
- ComputeContext 쪽 정렬: compute_context 규칙 적용 (#1779) → WS 우선 규약 강제 (#1780).
- ExecutionDomain default-safe 계약/E2E 테스트 추가 (#1775) + Core Loop 계약 스위트에 핵심 케이스로 편입 (#1789).
- 현재 상태: Phase 1까지 완료.

## Phase 2 – SubmitResult/WS SSOT 정리 (T1/T2 P0)
- [x] SubmitResult ↔ WS Envelopes 스키마 정렬/공용 모듈 (#1764, #1771) — CLOSED; shared WS/SDK 스키마 위치/명명 확정 후 downstream 뒤집힘 방지.
- [x] Runner/CLI/API가 WS 결과를 SSOT로 노출하도록 경로 정리 (#1770) — SubmitResult WS 우선 병합 + `precheck` 분리, CLI 출력 섹션 분리 완료.
- [x] SDK/CLI SubmitResult 출력 정리 (#1765) — downgrade/default-safe 신호 노출 + WS/Precheck 분리, 테스트 추가(#1789 연계).
- [x] SDK/전략 가이드 업데이트 (#1766) + ops/dev 가이드에서 “WS가 최종 진실”을 명시 (#1772) — ko/en 가이드에 WS SSOT vs pre-check 구분 및 런북 반영.

## Phase 3 – world 기반 데이터 preset 온램프 (T3 P0)
- [x] 이미 정의한 preset 스펙(#1776)을 기준으로 Runner/CLI Seamless 오토 구성 구현 (#1777) — `world.data.presets[]` → packaged `data_presets` 맵으로 매핑, `--data-preset` 옵션 추가, demo Seamless provider 기본 시드까지 자동 적용.
- [x] preset 기반 실행 예제/가이드 작성, CI/계약 테스트에서 실제로 도는 예제 붙이기 (#1778, #1789 연동) — core-loop demo world가 표준 data preset을 포함하고 계약 테스트에서 auto-wiring을 검증.

## Phase 4 – NodeID/TagQuery + Determinism 마무리 (T4/T5 P0)
- [x] NodeID/TagQuery 결정성 규칙 구현/검증: 엔진별 적용 (#1783) → 관측/테스트(#1784) — TagQueryNode NodeID가 query spec(정렬·중복 제거된 query_tags + match_mode + interval)에 따라 해시되도록 SDK/Gateway 정규화, queue_map match_mode 전달 및 결정성 테스트 추가.
- [x] Determinism 체크리스트 코드化 (#1785) → 관측 메트릭/대시보드 (#1786) → 런북 보강 (#1787) — NodeID CRC/필드/불일치·TagQuery 전용 메트릭 추가, `operations/determinism.md` 런북/architecture 링크로 대응 경로 명시.
- [x] Core Loop 계약 스위트에 NodeID/TagQuery·Determinism 관련 케이스 확장 (#1789) — Gateway determinism 메트릭이 NodeID 불일치 시 증가하는지 검증하는 계약 테스트 추가.

## Phase 5 – CI 게이트 정착 (T6 P0 마무리)
- [x] Core Loop 계약 스위트를 CI merge-blocker로 통합 (#1790) — `.github/workflows/ci.yml` `test` 잡에 `Core Loop contract suite` 스텝 추가, `CORE_LOOP_STACK_MODE=inproc`로 in-proc WS 스택을 구동해 실패 시 PR을 차단.
- [x] 로드맵/아키텍처 문서와 “이 테스트가 깨지면 어떤 방향성이 깨진 것인지”를 연결해 명시 (#1790) — 계약 스위트를 `docs/ko/design/core_loop_roadmap.md`(방향성), `docs/ko/architecture/architecture.md`(경계/SSOT), `docs/ko/operations/determinism.md`(런북)에서 참조하도록 정리해, 깨짐이 Core Loop 방향성과 어떤 연관이 있는지 바로 추적 가능.

### 병렬성 관점
- Phase 1(ExecutionDomain 라인)과 Phase 2(SubmitResult/WS SSOT)는 부분적으로 병렬 가능하지만,
- Phase 3(데이터 preset)·Phase 4(NodeID/Determinism)는 Phase 1/2에서 기본 규약이 잡힌 이후로 미는 쪽이 안전합니다.
