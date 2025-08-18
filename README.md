# qmtl-strategies

이 저장소는 [QMTL](https://github.com/hyophyop/qmtl) 전략 실험을 위한 템플릿 프로젝트입니다.

## QMTL 서브트리 동기화

프로젝트는 `qmtl` 서브트리를 포함합니다. 작업을 시작하기 전에 항상 최신 변경 사항을 가져오세요.

QMTL은 별도 저장소에서 가져온 서브트리로, 수정은 최소화하고 upstream 저장소에 반영된 뒤에만 동기화해야 합니다. 전략 레벨 최적화와 실험은 `qmtl/` 내부가 아닌 루트 디렉토리에서 수행하세요.

```bash
git fetch qmtl-subtree main
git subtree pull --prefix=qmtl qmtl-subtree main --squash
```
필요 시 `AGENTS.md`의 설정 절차를 참고해 `qmtl-subtree` 원격을 추가하세요.

## `qmtl init` 실행 방법

새 전략 프로젝트를 생성할 때는 `qmtl init` 명령을 사용합니다.

```bash
# 사용 가능한 템플릿 목록 확인
qmtl init --list-templates

# 브랜칭 템플릿과 샘플 데이터를 포함해 프로젝트 생성
qmtl init --path my_qmtl_project --strategy branching --with-sample-data
cd my_qmtl_project
```

생성된 디렉터리에는 `strategy.py`, `qmtl.yml`, `.gitignore`, 그리고 노드와 DAG를 정의하는 `strategies/nodes/`와 `strategies/dags/` 패키지가 포함됩니다. 기존 `generators/`, `indicators/`, `transforms/` 패키지는 `strategies/nodes/` 하위로 재배치되었습니다.

## 전략 템플릿 작성 절차

1. `strategies/example_strategy`를 참고해 새 전략 패키지를 작성합니다.
2. 패키지의 `__init__.py`에 `Strategy` 서브클래스를 구현합니다.

```python
from qmtl.sdk import Strategy

class MyStrategy(Strategy):
    def setup(self):
        pass
```

3. `strategies/strategy.py`를 수정하여 원하는 전략을 가져오고 실행합니다.

```python
from strategies.my_strategy import MyStrategy

if __name__ == "__main__":
    MyStrategy().run()
```

4. 환경 설정이 필요하면 `qmtl.yml`을 수정하고, 커스텀 노드를 `strategies/nodes/`에 추가한 뒤 DAG를 `strategies/dags/`에서 구성합니다. 기존 `generators/`, `indicators/`, `transforms/` 설명은 모두 `strategies/nodes/` 하위로 이동했습니다.
5. 전략이 정상 동작하는지 확인합니다.

```bash
python strategies/strategy.py
```

## 노드와 DAG 구성

노드 프로세서는 `strategies/nodes/`에, 전략 DAG는 `strategies/dags/`에 구성하며 자세한 방식은 [strategies/README.md](strategies/README.md)를 참고하세요.

## 추가 학습 자료

프로젝트 아키텍처 전반에 대한 설명은 [qmtl/architecture.md](qmtl/architecture.md) 문서를 참고하세요.

