# qmtl-strategies

이 저장소는 [QMTL](https://github.com/hyophyop/qmtl) 전략 실험을 위한 템플릿 프로젝트입니다.

## 하위 모듈 추가

프로젝트는 `qmtl` 서브모듈을 사용합니다. 저장소를 처음 클론했거나 최신 변경 사항을 받았을 때는 다음 명령으로 서브모듈을 초기화합니다.

```bash
git submodule update --init --recursive
```

새 프로젝트에 서브모듈을 추가하고 싶다면:

```bash
git submodule add https://github.com/hyophyop/qmtl.git qmtl
```

## `qmtl init` 실행 방법

새 전략 프로젝트를 생성할 때는 `qmtl init` 명령을 사용합니다.

```bash
# 사용 가능한 템플릿 목록 확인
qmtl init --list-templates

# 브랜칭 템플릿과 샘플 데이터를 포함해 프로젝트 생성
qmtl init --path my_qmtl_project --strategy branching --with-sample-data
cd my_qmtl_project
```

생성된 디렉터리에는 `strategy.py`, `qmtl.yml`, 그리고 `generators/`, `indicators/`, `transforms/` 패키지가 포함되어 확장 노드를 추가할 수 있습니다.

## 전략 템플릿 작성 절차

1. `strategies/example_strategy`를 참고해 새 전략 패키지를 작성합니다.
2. 패키지의 `__init__.py`에 `Strategy` 서브클래스를 구현합니다.

```python
from qmtl.sdk import Strategy

class MyStrategy(Strategy):
    def setup(self):
        pass
```

3. 루트의 `strategy.py`를 수정하여 원하는 전략을 가져오고 실행합니다.

```python
from strategies.my_strategy import MyStrategy

if __name__ == "__main__":
    MyStrategy().run()
```

4. 환경 설정이 필요하면 `qmtl.yml`을 수정하고, 커스텀 노드를 `generators/`, `indicators/`, `transforms/`에 추가합니다.
5. 전략이 정상 동작하는지 확인합니다.

```bash
python strategy.py
```

## 노드와 DAG 구성

노드 프로세서 정의와 DAG 조합 방식은 [strategies/README.md](strategies/README.md)를 참고하세요.

