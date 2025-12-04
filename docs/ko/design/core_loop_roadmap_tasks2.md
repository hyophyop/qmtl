# Core Loop 로드맵 잔여 이슈 우선순위 (tasks2)

Phase 5(CI 게이트)까지 완료했지만 #1755–#1788 사이 로드맵 이슈가 남아 있다. 2025-12-04 시점 상태를 기준으로, 전체 목록을 빠짐없이 포함해 우선순위를 재정렬했다.

## 현황 (#1755–#1788)
- **열린 이슈**: #1755, #1756, #1757, #1758, #1759, #1760, #1761, #1762, #1763, #1769, #1781, #1783, #1784, #1785, #1786, #1787, #1788.
- **닫힌 이슈**(참고): #1764, #1765, #1766, #1767, #1768, #1770, #1771, #1772, #1773, #1774, #1775, #1776, #1777, #1778, #1779, #1780, #1782. (게이트화는 #1790, 코어 케이스 추가는 #1789에서 이미 처리됨.)

## 권장 작업 순서

### 1) 입력/출력 규약 고정 (SubmitResult·ExecutionDomain 라인)
- #1755 SubmitResult 정규화 및 Core Loop 정렬로 출력 SSOT 확정.  
  - 닫기 요건: WS/Runner/SDK 출력 합치, 계약/CLI 스냅샷 업데이트, ko/en 가이드 링크 확인.
  - 작업: WS `DecisionEnvelope`/`ActivationEnvelope` 스키마를 공유 모듈로 끌어올리고 SubmitResult/CLI JSON이 동일하게 직렬화되도록 스냅샷 갱신(WS vs precheck 섹션 분리 유지).
- #1756, #1758 ExecutionDomain/effective_mode 힌트 제거·규칙 정렬로 입력 경계 단단히 하기.  
  - 닫기 요건: Runner/WS/CLI 입력 검증 통일, default-safe 강등 경로 보존, 퇴화 플래그 제거.
  - 작업: Runner/CLI에서 execution_domain 생략/모호 입력 시 compute-only 강등을 강제하고, SDK effective_mode 힌트/옵션을 제거한 뒤 계약 테스트로 검증.
- #1760 ComputeContext/ExecutionDomain 규칙 정렬을 바로 이어 적용.  
  - 닫기 요건: compute_context 규칙이 Gateway/DM/SDK에 동일하게 적용되고 계약 테스트로 검증.
  - 작업: ComputeContext 허용 필드/우선순위를 ExecutionDomain 규약과 동일하게 중앙 정의하고, Gateway/DM/SDK 파이프라인에서 shared validator를 사용하도록 통일.
- #1769 SDK/CLI 모드·도메인 문서 갱신으로 표면 정합성 확보.  
  - 닫기 요건: ko/en 동시 갱신, 예제/옵션 표 최신화, `docs-link-check` 통과.
  - 작업: mode/domain 옵션 표를 ExecutionDomain default-safe 규칙 기준으로 다시 쓰고 CLI/SDK 예제 출력과 연결.

- **실행 순서/체크**  
  - (1) 출력 라인(#1755) 정규화·스냅샷 갱신 → (2) 입력 라인(#1756/#1758) 검증·힌트 제거 → (3) ComputeContext 규칙 전파(#1760) → (4) 표면/문서 정리(#1769).  
  - 테스트: `uv run mkdocs build --strict`, `CORE_LOOP_STACK_MODE=inproc uv run -m pytest -q tests/e2e/core_loop -q`, 필요 시 CLI JSON 스냅샷 갱신 커맨드까지 한 번에 실행.

### 2) 평가/활성·데이터 온램프
- #1757 평가/활성 흐름 정렬(WS 우선·SSOT 연결)로 상단 플로우 정리.  
  - 닫기 요건: WS 평가/활성 스키마/흐름이 SubmitResult와 일관, 계약 테스트/가이드 정합성 확보.
  - 작업: WS `DecisionEnvelope`/`ActivationEnvelope` → `SubmitResult.ws.*` 매핑 샘플과 CLI `--output json` 출력이 동일함을 상단 가이드에 명시하고, ValidationPipeline `precheck` 분리 규칙을 `tests/e2e/core_loop` 계약 테스트와 함께 고정(activation TTL/etag/run_id 포함).
- #1759 world 기반 데이터 preset 온램프는 상단 규약이 안정된 뒤 진행.  
  - 닫기 요건: preset 자동 연결 경로가 Runner/CLI 예제에서 동작, 계약/예제 테스트 추가 또는 확증.
  - 작업: `world.data.presets[]` → Runner/CLI Seamless 오토 구성 흐름을 `qmtl submit --world ... --data-preset ...` 예제와 함께 문서화하고, preset 누락/불일치 시 fail-closed 및 demo world 기반 계약 테스트로 확인.

### 3) 결정성/TagQuery 클러스터
- #1761, #1783 NodeID/TagQuery 결정성 적용(엔진/SDK/Gateway) → #1784 관측/테스트로 검증 사슬 완성.  
  - 닫기 요건: NodeID/TagQuery 정규화 코드 일치, 결정성 메트릭 상승 케이스 계약 테스트 포함, 관측 대시보드 훅.
- #1785, #1762 결정성 체크리스트 구현·스코프 종료 → #1786 메트릭/대시보드 → #1787 런북 업데이트 순으로 일괄 마감.  
  - 닫기 요건: 체크리스트 항목 코드 반영, 대시보드 패널 추가, `operations/determinism.md` 갱신, 계약/ops 문서 링크 정리.

### 4) 계약 스위트 보강·마감
- #1788 계약 테스트 스켈레톤을 현재 게이트 기준에 맞춰 정리(스킵/flake 정돈).  
  - 닫기 요건: 필요 없는 xfail/skip 제거, CI gate에서 안정 통과 확인.
- #1781 ComputeContext 계약 테스트로 커버리지 확정.  
  - 닫기 요건: compute_context 규칙 위반 시 실패하는 케이스 추가, inproc 스택/CI에서 통과 확인.
- #1763 메타 에픽은 위 작업 반영 후 상태 업데이트·종료.  
  - 닫기 요건: 자식 이슈 링크 상태 반영, 문서/게이트 안내 정리, 닫기 코멘트에 테스트 로그 요약.

## 운영 메모
- 계약 스위트는 이미 CI merge-blocker이므로, 각 이슈를 닫기 전에 `CORE_LOOP_STACK_MODE=inproc uv run -m pytest -q tests/e2e/core_loop -q`로 회귀 여부를 확인한다.
- 결정성/TagQuery 관련 변경은 `docs/ko/operations/determinism.md` 반영 여부를 동시에 체크한다.
- 닫기 코멘트에는 실행한 테스트 요약(`mypy`, `mkdocs build --strict`, 계약 스위트 등)과 ko/en 문서 동기화 여부를 함께 남긴다.
