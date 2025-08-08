# Development Guidelines

This repository hosts strategy experiments built on top of the [QMTL](qmtl/README.md) subtree. Use this document to keep workflows consistent and to leverage QMTL effectively.

## QMTL 서브트리 최신화 정책 (필수)

이 저장소는 전략 개발과 동시에 QMTL 자체의 문제/개선을 즉시 반영하기 위한 목적을 갖습니다. 따라서 `qmtl` 서브트리는 항상 원격 최신 상태를 기준으로 작업해야 합니다.

- 작업(탐색, 코딩, 테스트) 시작 전 반드시 서브트리를 최신으로 동기화하세요.
  ```bash
  # 서브트리 원격 저장소에서 최신 변경사항 가져오기
  git fetch qmtl-subtree main
  # 서브트리 업데이트 (스쿼시 방식)
  git subtree pull --prefix=qmtl qmtl-subtree main --squash
  ```
- 서브트리 갱신으로 변경사항이 있으면 루트 리포지토리에 커밋하세요.
  ```bash
  git add qmtl
  git commit -m "chore: bump qmtl subtree to latest"
  ```
- 전략 개발 중 QMTL의 버그/개선이 확인되면, 우선 `qmtl/` 서브트리 내에 수정과 테스트를 추가하고, 루트 전략 테스트도 함께 갱신합니다. 변경 사항을 반영한 뒤 위 절차로 서브트리를 업데이트하세요.
- PR 체크리스트에 다음을 포함하세요.
  - [ ] `git log --oneline qmtl/ -n 3` 결과가 원격 최신과 일치함을 확인
  - [ ] QMTL 변경 시 `qmtl/tests`와 루트 `tests` 모두 통과

### 빠른 점검 명령어

```bash
# 현재 서브트리 상태 확인
git log --oneline qmtl/ -n 3

# 원격 최신과 로컬 비교
git fetch qmtl-subtree main
git log --oneline qmtl-subtree/main -n 3
```

## Setup

- Initialize the subtree after cloning:
  ```bash
  git remote add qmtl-subtree https://github.com/hyophyop/qmtl.git
  git fetch qmtl-subtree
  git subtree add --prefix=qmtl qmtl-subtree main --squash
  ```
  그리고 항상 최신을 반영하려면(매 작업 시작 전 권장):
  ```bash
  git subtree pull --prefix=qmtl qmtl-subtree main --squash
  ```
- Manage dependencies with [uv](https://github.com/astral-sh/uv):
  ```bash
  uv pip install -e qmtl[dev]
  ```
  Install additional packages in the same environment when needed.

## Development Practices

- Follow the Single Responsibility Principle for every strategy, generator, indicator and transform.
- Add reusable components under `strategies/`, `generators/`, `indicators/` or `transforms/`. Place tests in `qmtl/tests/` or a local `tests/` directory.
- Manage node processors under `strategies/nodes/` and define strategy DAGs in `strategies/dags/`.
- Refer to `qmtl/architecture.md`, `qmtl/gateway.md` and `qmtl/dag-manager.md` for design details before modifying core behavior.
- See [strategies/README.md](strategies/README.md) for guidance on building and reusing node processors and DAGs.
- Use descriptive names and the `*_dsn` suffix for connection strings.
- When proposing task lists or improvements, highlight opportunities for parallel execution.
- Ensure resources such as network or database connections are closed to avoid `ResourceWarning`.
- 전략 개발 중 QMTL 이슈가 발견되면, 서브트리를 최신으로 동기화한 뒤 `qmtl/` 내부에서 우선 수정하고 테스트하세요. qmtl은 서브트리이지만 별도 구성된 프로젝트이므로 `qmtl/AGENTS.md`의 가이드를 충실히 따라 수정/테스트/커밋/PR을 진행해야 합니다. 수정 후 루트 리포지토리에 서브트리 변경사항을 커밋하는 것을 잊지 마세요.

## Testing

- Run the full test suite and treat warnings as errors:
  ```bash
  uv run -m pytest -W error
  ```
- Any change to node processors requires running their tests. Place tests under `strategies/tests/nodes/` and run them with:
  ```bash
  uv run -m pytest strategies/tests/nodes -W error
  ```
- Commit only after tests pass without warnings.

## Running Strategies

- Update `strategy.py` to execute your strategy and verify with:
  ```bash
  python strategy.py
  ```

## 서브트리 관리

### 서브트리 업데이트
```bash
# 최신 변경사항 가져오기
git fetch qmtl-subtree main

# 서브트리 업데이트 (스쿼시 방식)
git subtree pull --prefix=qmtl qmtl-subtree main --squash
```

### 서브트리 변경사항 푸시
```bash
# 로컬 변경사항을 서브트리 원격 저장소에 푸시
git subtree push --prefix=qmtl qmtl-subtree main
```

### 서브트리 상태 확인
```bash
# 서브트리 커밋 히스토리 확인
git log --oneline qmtl/ -n 5

# 원격과 로컬 비교
git log --oneline qmtl-subtree/main -n 3
```

