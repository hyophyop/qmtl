# Codex Issue Runner

QMTL 리포지토리에서 정의된 이슈 목록을 바탕으로 Codex CLI를 사용해 자동으로 작업을 수행하고 검증까지 진행하는 방법을 정리합니다. 본 가이드는 이슈별 병렬 오케스트레이터 스크립트 경로만을 제공합니다.

## 개요
- 목적: `qmtl/` 하위만 수정하며, 각 이슈의 변경, 테스트, 문서 빌드까지 단일 흐름으로 수행.
- 스코프 파일: 기본은 `docs/issues/scope.md`이며, `ISSUE_SCOPE_FILE`로 경로를 바꿀 수 있습니다.

## 이슈별 병렬 실행(권장)
- 스크립트가 이슈마다 별도 `codex exec` 프로세스를 생성하고, git worktree로 작업 영역을 격리합니다.
- 로그/변경/검증 결과는 `-o/--outdir`로 지정한 폴더에 이슈별로 저장됩니다.
- 명령 예시:

```
bash scripts/run_codex_issues.sh \
  -f docs/issues/scope.md -i "755 756 757" \
  --parallel auto -o .codex_runs
```

- 검증까지 포함:

```
bash scripts/run_codex_issues.sh \
  -f docs/issues/scope.md -i "755 756" \
  --verify --parallel 2 -o .codex_runs
```

### PR 전략: 기본값 = 이슈별 Draft PR

- 기본 동작: 각 이슈에 대해 Draft PR을 생성하고, 후속 패스에서 동일 브랜치를 업데이트합니다(issue/<ID>-codex). 각 패스의 `.last.txt`는 PR 코멘트로 추가됩니다.
- PR 생성은 "변경이 있을 때만" 수행합니다. 빈 커밋으로 PR을 만들지 않습니다.
- 완료(Done) 상태에서 자동 머지하려면 `--merge`를 추가하세요.

예시(자동 머지 포함):

```
bash scripts/run_codex_issues.sh \
  -f docs/issues/scope.md -i "761 762 763" \
  --parallel auto -o .codex_runs --merge
```

## 산출물
- 마지막 메시지: `.codex_runs/<ISSUE>.pass<idx>.last.txt`
- 변경 요약: `.codex_runs/<ISSUE>.pass<idx>.changes.txt`
- 검증 로그(옵션 `--verify`): `.codex_runs/<ISSUE>.pass<idx>.verify.txt`
 - 콘솔 로그: `.codex_runs/<ISSUE>.pass<idx>.console.txt` (보존용·의사결정에 사용하지 않음)

> 주의: `.codex_runs/`와 `.codex_worktrees/`는 리포에 커밋하지 않습니다. `.gitignore`에 두 경로가 포함되어 있어야 하며, 오케스트레이터의 커밋 로직은 해당 디렉터리를 스테이징에서 자동 제외합니다.

## 스크립트 주요 옵션
- `--parallel N`: 동시에 실행할 이슈 개수(기본 auto). CPU/이슈 수에 맞춰 자동 제한.
- `--verify`, `--verify-full`: 프리플라이트/풀 테스트와 문서 빌드 수행.
- `--json`: Codex JSON 스트리밍 활성화(마지막 메시지 아카이브).
- `--cleanup-worktrees`: 완료 후 생성한 git worktree 정리.
- `--pr`, `--merge`: Done 상태인 이슈에 대해 PR 생성/자동 머지(자격 요구).
- `--stash-wip`: 부모 워킹 트리 변경사항을 임시 스태시 후 복구.

## 요구 사항
- Codex CLI가 PATH에 있어야 합니다: `codex --version`
- Python/의존성은 uv로 관리합니다: `uv pip install -e .[dev]`
- 문서 빌드에 mkdocs 및 플러그인이 필요합니다(dev extras 포함).

## CI 연계(선택)
이슈 목록 파일이 있을 때에만 자동 실행하도록 조건부로 트리거할 수 있습니다.

```
test -n "$ISSUE_SCOPE_FILE" || ISSUE_SCOPE_FILE=docs/issues/scope.md; \
if [ -f "$ISSUE_SCOPE_FILE" ]; then \
  IDS=$(awk '/^- ID:/{print $3}' "$ISSUE_SCOPE_FILE" | paste -sd ' ' -); \
  bash scripts/run_codex_issues.sh -f "$ISSUE_SCOPE_FILE" -i "$IDS" --parallel auto -o .codex_runs; \
else \
  echo "No issue list; skipping Codex issue runner."; \
fi
```

## 오케스트레이터/워커 경계 및 출력 계약

- 블랙박스 원칙: 워커(Codex 실행)는 블랙박스로 취급하며, 오케스트레이터는 산출물만 소비합니다.
- 아티팩트 기반 판정: 상태(Done/Needs follow‑up/Blocked)는 오케스트레이터가 `.changes/.verify`와 `Next-run Instructions` 유무를 바탕으로 결정합니다. 워커의 상태 라인은 참고용입니다.
- 워커 푸터(간결):
  - `Suggested commit message` 섹션(완료 시 `Fixes #<ISSUE_ID>`, 그 외 `Refs #<ISSUE_ID>`)
  - 선택: `Next-run Instructions`(후속 작업이 필요할 때만)
- 예시 푸터:

```
Suggested commit message
Fixes #755: chore(dag-manager): add idempotent neo4j migrations and docs

Result status: Done  
(참고용; 최종 판정은 오케스트레이터가 수행)
```

> 참고: 오케스트레이터는 `.last.txt`에 `Result status:`가 없더라도 `Next-run Instructions` 섹션이 있으면 후속 실행이 필요하다고 판단하도록 보완되어 있습니다.

## 주의사항
- 스크립트 경로는 “병렬 전용”입니다. 여러 이슈를 동시에 처리하려면 반드시 `scripts/run_codex_issues.sh`를 사용하세요.
- 베이스 브랜치/리모트 구성이 없다면 `--git-base`를 명시해 로컬 기준으로 워크트리를 만들 것을 권장합니다.
- 워킹 트리가 깨끗하지 않으면 기본적으로 실패합니다. 필요 시 `--stash-wip`를 사용하세요.
