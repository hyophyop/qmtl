# Contributing Guide

This project demonstrates how to build and test QMTL strategy packages. It also
serves as the canonical reference for shared policies—including the QMTL
subtree workflow, testing commands, and the AlphaDocs process.

## AGENTS front-matter template

All `AGENTS.md` files must begin with a front-matter block that captures their
scope and review metadata:

```
---
scope: <directory or project scope>
last-reviewed: YYYY-MM-DD
canonical-guidelines: <relative link to CONTRIBUTING.md>
---
```

Include this block at the top of new or modified `AGENTS.md` files to keep
instructions consistent across the repository.

## CI 상태 및 로컬 검증

GitHub Actions가 push/pull_request 이벤트에서 자동으로 실행됩니다. 아래 로컬 체크는 PR 전에 빠르게 검증할 때 사용하세요.

- 의존성/환경 준비(또는 `scripts/bootstrap.sh` 사용):
  ```bash
  pip install uv pre-commit
  uv venv
  uv pip install -e qmtl[dev]
  uv pip install pyyaml
  ```
- Lint:
  ```bash
  uv run pre-commit run --files $(git ls-files '*.py')
  uv run qmtl check-imports
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
  CI도 위 검사들을 실행하며 실패 시 워크플로우가 실패합니다.

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

## Testing

- Run the full test suite and treat warnings as errors:
  ```bash
  uv run -m pytest -W error
  ```
- Any change to node processors requires running their tests. Place tests under
  `strategies/tests/nodes/` and run them with:
  ```bash
  uv run -m pytest strategies/tests/nodes -W error
  ```
- Commit only after tests pass without warnings.

## AlphaDocs Workflow

1. 모든 연구 문서는 `docs/alphadocs/`에 저장하고
   `docs/alphadocs_registry.yml`에 `doc`, `status`, `modules` 필드를 갖는 항목을
   추가합니다.
2. 문서를 근거로 코드를 작성할 때는 해당 모듈 상단에
   `# Source: docs/alphadocs/<doc>.md` 주석을 포함합니다.
3. 각 문서는 필요한 transform 이름과 테스트 범위를 정리한 `QMTL Integration`
   섹션을 포함합니다.
4. 구현이 완료되면 레지스트리의 `status`와 `modules` 목록을 갱신하고 관련
   테스트를 추가합니다.
   
   개발자 워크플로 (구현 후 필수)
   --------------------------------
   - 구현이 완료된 모듈을 레지스트리에 등록하고 상태와 이력 로그를 자동으로 갱신하려면 아래 명령을 사용하세요:

   ```bash
   # 예시: 모듈 등록 및 상태 변경, 이력 로그 추가
   python scripts/manage_alphadocs.py register-module --doc <DOC_PATH> --module <MODULE_PATH>

   # 문서 동기화 검사 실행
   uv run scripts/check_doc_sync.py
   ```

   - 문서를 이동/이름 변경한 경우:

   ```bash
   python scripts/manage_alphadocs.py record-history --old <OLD_PATH> --new <NEW_PATH> --reason "이유"
   ```

   위 단계를 PR에 포함시키면 리뷰어가 레지스트리·이력 동기화가 완료되었음을 쉽게 확인할 수 있습니다.

5. 문서를 이동하거나 이름을 변경할 경우
   `docs/alphadocs_history.log`에 날짜, 이전 경로, 새 경로, 사유를 기록하고,
   주석과 레지스트리 경로도 함께 수정합니다.
6. PR에는 레지스트리와 소스 주석 동기화를 확인했다는 체크 항목과
   `uv run scripts/check_doc_sync.py` 실행 결과를 포함합니다.
7. 알파 문서는 구현에 사용된 위험(hazard), 방향(direction), 비용/체결(cost/fill)
   등 모든 수학적 공식을 빠짐없이 포함해야 하며, 코드 노드는 이러한 공식을
   참조하여 외부 데이터 입력에만 의존하지 말고 직접 구현해야 합니다. PR은
   문서와 코드의 일치성을 보여주고 공식 구성요소를 다루는 테스트를 포함해야
   합니다.

### Idea directories

- `docs/alphadocs/ideas/` 폴더는 아이디어 기록을 위한 버전 관리 대상일 뿐
  직접 구현하지 않습니다.
- 더 높은 성능의 모델로 정제된 아이디어(예:
  `docs/alphadocs/ideas/gpt5pro/`)만 구현 대상으로 간주합니다.

### Prioritizing GPT-5-Pro Generated Ideas

- `docs/alphadocs/ideas/gpt5pro/` 디렉터리에는 강한 모델(GPT-5-Pro)이 검토한
  알파 아이디어가 들어 있습니다. 다음 원칙을 따릅니다:
  - 레지스트리에 `status: prioritized`와 `source_model: gpt5pro`를 설정합니다.
  - 코드에 `# Source: docs/alphadocs/ideas/gpt5pro/<doc>.md`와
    `# Priority: gpt5pro` 주석을 추가합니다.
  - 에이전트는 `docs/alphadocs_history.log`에 이동/이름 변경 이력을 기록하고
    구현 이슈나 브랜치를 자동으로 생성합니다.
  - 이러한 아이디어를 구현한 PR에는 에이전트 실행 로그(도구 이름, 모델,
    타임스탬프, 수행한 작업 요약)를 포함합니다.

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

에이전트/개발자 대상 요약 지침을 `docs/agents-instructions.md`에 수록했습니다. `AGENTS.md` 파일을 수정했다면 `uv run python scripts/build_agent_instructions.py`로 이 문서를 갱신한 뒤 커밋하세요. GitHub 템플릿과 PR/Issue 지침은 `.github/` 디렉터리를 확인하세요.
