# Contributing Guide

This project demonstrates how to build and test QMTL strategy packages.

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
