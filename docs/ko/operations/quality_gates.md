---
title: "품질 게이트"
tags:
  - operations
  - quality
  - ci
author: "QMTL Team"
last_modified: 2026-04-08
---

{{ nav_links() }}

# 품질 게이트

이 문서는 QMTL 저장소의 품질 검사를 `PR 하드 게이트`, `보고서 전용 신호`, `파일럿 워크플로`로 구분해 정리합니다. 기준 문서는 한국어(`docs/ko/...`)이며 영어 문서는 동일 구조의 번역본입니다.

## 게이트 분류

| 구분 | 도구/체크 | 현재 강제 수준 | 목적 |
| --- | --- | --- | --- |
| PR 하드 게이트 | Ruff, deptry, radon diff, mypy, docs/link/i18n/import-cycle checks, packaging smoke, pytest/e2e suites | 실패 시 PR 차단 | 회귀를 즉시 차단해야 하는 저잡음 신호 |
| 보고서 전용 신호 | branch coverage baseline, Bandit, Vulture | PR 차단 없음, artifact/summary만 생성 | 베이스라인 수집과 노이즈 분류 |
| 파일럿 워크플로 | mutmut (`gateway/sdk/pipeline`) | 별도 워크플로, report-only | mutation survivor 패턴과 실행 비용 측정 |

## 스캔 범위 정책

| 도구 | 기본 스캔 범위 | 기본 제외 범위 | 정책 근거 |
| --- | --- | --- | --- |
| Ruff | 저장소 전체 | `notebooks/*.ipynb`, `qmtl/foundation/proto/*_pb2*.py` | 생성 코드와 노트북은 repo-wide hard gate 노이즈가 크므로 제외 |
| deptry | `qmtl/` | `qmtl/examples`, 서비스 테스트, generated proto | 런타임 의존성 위생을 production package 기준으로 측정 |
| coverage.py | `qmtl/` | `qmtl/examples`, generated proto | 테스트는 실행 입력이지만 분모는 production package에 한정 |
| Bandit | `qmtl/`, `scripts/`, `main.py`, `conftest.py` | `tests/`, `notebooks/`, `qmtl/examples/`, generated proto, `build/`, `dist/` | 보안 신호는 운영 코드와 운영 스크립트까지 포함 |
| Vulture | `qmtl/` | `tests/`, `notebooks/`, `qmtl/examples/`, generated proto, `build/`, `dist/` | dead-code 탐지는 스크립트/테스트까지 넣으면 false positive가 급증 |
| mutmut | `qmtl/runtime/sdk`, `qmtl/runtime/pipeline`, `qmtl/services/gateway` | generated proto | 고변동 핵심 경로만 pilot 대상으로 제한 |

### 범위 결정 원칙

- `examples/`, `notebooks/` 는 학습/데모 산출물로 간주하며 PR 하드 게이트의 분모에 넣지 않습니다.
- generated code(`qmtl/foundation/proto/*_pb2*.py`, `*_pb2_grpc.py`)는 수동 유지보수 대상이 아니므로 repo-wide 정적 신호에서 기본 제외합니다.
- `tests/` 는 커버리지 입력과 mutation 방어선 역할은 하지만, dead-code/security 리포트의 기본 스캔 대상로는 취급하지 않습니다.
- 새 품질 도구를 추가할 때는 먼저 이 표에 스캔 범위와 제외 규칙을 기록한 뒤 CI에 연결합니다.

## 현재 실행 경로

### PR 하드 게이트

- GitHub Actions: [`.github/workflows/ci.yml`]({{ code_url('.github/workflows/ci.yml') }})
- 로컬 parity: [`scripts/run_ci_local.sh`]({{ code_url('scripts/run_ci_local.sh') }})

두 경로 모두 다음을 공통으로 수행합니다.

- Ruff / deptry / radon diff / mypy
- docs strict build 및 링크/설계/i18n 체크
- packaging smoke
- pytest preflight
- 본 테스트 + `world_smoke` + `core_loop`
- branch coverage baseline 요약 생성
- Bandit / Vulture report-only 산출물 생성

### mutation pilot

- 워크플로: [`.github/workflows/mutation-pilot.yml`]({{ code_url('.github/workflows/mutation-pilot.yml') }})
- 로컬 실행: `bash scripts/run_mutation_pilot.sh`
- 선택적 selector 예시: `bash scripts/run_mutation_pilot.sh --selector 'qmtl.runtime.pipeline*'`
- 해석 원칙: pilot은 report-only이므로 `exitcode.txt` 가 0이 아니어도 PR 하드 게이트를 막지 않습니다. 대신 `summary.md` 에 첫 실패 테스트와 초기 triage 분류를 남깁니다.

## 산출물 위치

- coverage: `.artifacts/quality-gates/coverage/`
  - `coverage.json`, `coverage.xml`, `coverage.txt`
  - `summary.json`, `summary.md`
- Bandit: `.artifacts/quality-gates/security/bandit.json`
- Vulture: `.artifacts/quality-gates/deadcode/`
  - `vulture.txt`, `vulture.exitcode`
  - `summary.json`, `summary.md`
- mutmut pilot: `.artifacts/quality-gates/mutation/`
  - `mutmut.log`, `exitcode.txt`, `summary.md`, 필요 시 `mutants.tgz`
  - `summary.md` 는 최신 실행의 첫 실패 테스트와 `tooling noise` 여부를 함께 기록합니다.

## 단계적 롤아웃 기준

### branch coverage

- 현재 단계: report-only baseline 수집
- 다음 단계 후보:
  1. 전체 `qmtl` branch coverage baseline을 2회 이상 연속 수집
  2. 핵심 경로(`runtime/sdk`, `runtime/pipeline`, `services/gateway`)별 baseline 분산 확인
  3. 변동폭이 작은 focus area부터 floor를 도입

### Bandit / Vulture

- 현재 단계: report-only
- 승격 조건:
  - false positive 분류 규칙이 문서화되어 있고
  - 반복적으로 같은 잡음이 suppress/allowlist 없이 정리되며
  - 신규 이슈만 구분 가능한 baseline 운영이 가능할 때
- triage 기준:
  - `Bandit / needs fix`: 운영 경로에서의 credential 처리, shell injection, unsafe deserialization, 과도한 파일 권한은 우선 수정 대상으로 분류합니다. 예를 들어 사용자 입력이 들어가는 shell 호출은 suppress 없이 코드 수정이 필요합니다.
  - `Bandit / accepted risk`: 제한된 subprocess 호출이나 임시 파일 사용처럼 의도가 명확하고 경계가 좁은 경우만 중앙 설정과 triage 메모에 근거를 남기고 유지합니다. 예를 들어 고정된 내부 명령 실행은 근거를 남긴 뒤 중앙 설정으로만 예외 처리합니다.
  - `Bandit / tooling noise`: 테스트·예제·generated 경로가 잘못 스캔된 경우는 inline ignore 대신 스캔 범위를 먼저 조정합니다.
  - `Vulture / candidate cleanup`: 참조가 없는 helper, import, local variable은 우선 삭제 후보로 처리합니다. 실제 실행 경로에서 도달 증거가 없으면 cleanup PR에 포함합니다.
  - `Vulture / keep but document`: 외부 CLI 진입점, 호환성 shim, reflection/dynamic import hook은 문서화한 뒤 유지합니다. 예를 들어 plugin registry에서 문자열 기반으로 로딩되는 hook은 근거 문서를 남기고 유지합니다.
  - `Vulture / false positive`: framework entrypoint, plugin registry, 런타임 동적 로딩으로만 도달하는 심볼은 suppress 전에 두 번 이상 반복되는지 확인합니다.
- 분류 후 액션:
  - `Bandit / needs fix`, `Vulture / candidate cleanup`: 다음 코드 변경 묶음에서 바로 수정하거나 제거합니다.
  - `Bandit / accepted risk`, `Vulture / keep but document`: 중앙 설정과 문서 근거를 함께 남기고 다음 baseline 갱신 때 재확인합니다.
  - `Bandit / tooling noise`, `Vulture / false positive`: suppress 전에 같은 finding이 반복되는지 확인하고, 반복되면 스캔 범위 또는 baseline 규칙을 조정합니다.

### mutmut

- 현재 단계: 별도 workflow 기반 pilot
- survivor 분류:
  - missing assertion
  - equivalent mutant
  - integration gap
  - flaky / tooling noise
- survivor 예시:
  - `missing assertion`: 반환값이나 branch 조건이 바뀌어도 테스트가 통과한다면 assertion 강도가 부족한 것으로 분류합니다. 조치는 해당 관찰 결과를 직접 검증하는 assertion을 추가하는 것입니다.
  - `equivalent mutant`: 도메인 제약상 동치인 비교 연산 변경처럼 관찰 가능한 의미 변화가 없는 경우입니다. 조치는 `equivalent`로 기록하고 gate 분모에서 분리할지 검토하는 것입니다.
  - `integration gap`: 단위 테스트는 통과하지만 cross-service contract나 adapter 경계가 검증되지 않아 mutant가 살아남는 경우입니다. 조치는 contract 또는 integration test를 추가하는 것입니다.
  - `flaky / tooling noise`: 현재 pilot에서 관찰된 `tagquery_manager.stop()/poll_loop` cancellation 경로처럼 runner 특성으로 결과가 흔들리는 경우입니다. 조치는 재현성 확인 뒤 tooling noise로 유지하거나 runner/workflow 안정화 작업으로 넘기는 것입니다.
- gate 제안 조건:
  - 실행 시간과 flake rate가 안정적일 것
  - equivalent mutant 비율이 관리 가능할 것
  - 최소 한 개 focus area에서 재현 가능한 baseline이 확보될 것

## ignore / waiver 정책

- 하드 게이트 도구의 예외는 설정 파일(`pyproject.toml`, `.bandit`)에 중앙화하고, ad-hoc CLI 인수로 숨기지 않습니다.
- report-only 신호의 예외는 먼저 artifact와 triage 메모로 누적한 뒤, 반복 노이즈가 확인되면 설정에 반영합니다.
- mutation survivor를 무시할 때는 `equivalent`, `not worth gating`, `needs test`, `tooling noise` 중 하나로 분류해 남깁니다.

관련 실행 환경과 기본 CI 설명은 [CI 환경](ci.md)을 참고하세요.

{{ nav_links() }}
