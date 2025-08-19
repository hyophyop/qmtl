# Contributing Guide

This project demonstrates how to build and test QMTL strategy packages.

## 공지: GitHub CI 일시 비활성화 (2025-08-14)

레포지토리의 GitHub Actions 자동 트리거(push/pull_request)가 임시로 비활성화되었습니다. 현재 워크플로우는 수동(workflow_dispatch)으로만 실행됩니다. PR 생성/업데이트 시 자동 검증이 수행되지 않으므로, 아래 로컬 체크를 직접 수행한 뒤 푸시/PR을 생성해 주세요.

- 의존성/환경 준비:
   ```bash
   pip install uv pre-commit
   uv venv
   uv pip install -e qmtl[dev]
   uv pip install pyyaml
   ```
- Lint:
   ```bash
   uv run pre-commit run --files $(git ls-files '*.py')
   ```
- 테스트:
   ```bash
   uv run -m pytest -W error
   ```
- 문서 동기화 체크:
   ```bash
   uv run scripts/check_doc_sync.py
   uv run qmtl/scripts/check_doc_sync.py
   ```
   PR에서 `docs/` 경로를 수정하면 GitHub Actions가 이 스크립트를 자동 실행하며 실패 시 워크플로우가 실패합니다.

CI가 재활성화되면 본 문서에서 안내를 갱신하겠습니다.

## QMTL 서브트리 최신화 및 변경 원칙 (필수)

이 저장소는 전략 개발과 동시에 QMTL 개선을 병행합니다. 따라서 `qmtl` 서브트리는 항상 최신 상태를 유지해야 하며, 서브트리 내부 변경 시에는 별도 프로젝트로 간주하여 해당 프로젝트의 가이드를 엄격히 따라야 합니다.

- 작업 시작 전 서브트리 최신화:
  ```bash
  git fetch qmtl-subtree main
  git subtree pull --prefix=qmtl qmtl-subtree main --squash
  ```
- `qmtl/` 내부 수정 시: `qmtl/AGENTS.md`의 가이드를 충실히 따르고, 테스트(`qmtl/tests`)를 통과시킨 뒤 루트 저장소에서 서브트리 변경 사항을 커밋하세요.
  ```bash
  git add qmtl && git commit -m "chore: bump qmtl subtree to latest"
  ```
- QMTL 원본 저장소 반영 흐름:
  1. 변경이 필요하면 [QMTL 원본 저장소](https://github.com/hyophyop/qmtl)에 이슈를 등록하거나 PR을 생성해 변경 계획을 공유합니다.
  2. 로컬 수정 내용을 `git subtree push --prefix=qmtl qmtl-subtree main`으로 upstream에 푸시하고 해당 저장소에서 PR을 만듭니다.
  3. PR이 병합되면 아래 명령으로 서브트리를 최신화하고 커밋합니다.
     ```bash
     git fetch qmtl-subtree main
     git subtree pull --prefix=qmtl qmtl-subtree main --squash
     git add qmtl && git commit -m "chore: bump qmtl subtree to latest"
     ```
- PR 체크리스트 권장 항목:
  - [ ] `git log -n 3 --oneline qmtl/` 결과 확인(원격 최신 반영)
  - [ ] `uv run -m pytest -W error` 실행 후 `qmtl/tests`와 루트 `tests` 모두 통과

## Setting up the QMTL CLI

1. Initialize the QMTL subtree (once):
   ```bash
   git remote add qmtl-subtree https://github.com/hyophyop/qmtl.git
   git subtree add --prefix=qmtl qmtl-subtree main --squash
   ```
2. Install the CLI in editable mode to expose the `qmtl` command:
   ```bash
   uv pip install -e qmtl[dev]
   ```
3. Verify the command works:
   ```bash
   qmtl --help
   ```

> 서브트리 최신화: 위 초기화 이후에도 매 작업 시작 전에 `git fetch qmtl-subtree main`과 `git subtree pull --prefix=qmtl qmtl-subtree main --squash`를 수행하는 것을 권장합니다.

## Adding a new strategy

1. Copy `strategies/example_strategy` to a new folder, e.g. `strategies/my_strategy`.
2. Implement your strategy class inside `__init__.py`.
3. Update `strategy.py` to import and run your strategy:
   ```python
   from my_strategy import MyStrategy

   if __name__ == "__main__":
       MyStrategy().run()
   ```
4. Run the strategy to ensure it executes correctly:
   ```bash
   cd strategies
   python strategy.py
   ```

---

### 서브트리 최신화 각주

이 저장소의 모든 문서/가이드/README는 "서브트리 최신화" 원칙을 전제로 합니다. `qmtl` 서브트리 변경 시 반드시 루트 저장소에 커밋하고, 변경된 QMTL 코드에 대해서는 `qmtl/AGENTS.md`의 정책과 테스트 지침을 준수하세요.

## 추가 안내

에이전트/개발자 대상 요약 지침을 `docs/agents-instructions.md`에 수록했습니다. GitHub 템플릿과 PR/Issue 지침은 `.github/` 디렉터리를 확인하세요.
