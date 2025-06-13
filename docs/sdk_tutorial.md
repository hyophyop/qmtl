# SDK 사용 가이드

본 문서는 QMTL SDK를 이용해 전략을 구현하고 실행하는 기본 절차를 소개합니다. 보다 상세한 아키텍처 설명과 예시는 `architecture.md`와 `examples/` 디렉터리를 참고하세요.

## 설치

```bash
uv venv
uv pip install -e .[dev]
```

## 기본 구조

SDK를 사용하려면 `Strategy` 클래스를 상속하고 `setup()`과 `define_execution()` 메서드를 구현합니다. 노드는 `StreamInput`, `Node`, `TagQueryNode` 등을 이용해 정의하며 모든 노드는 하나 이상의 업스트림을 가져야 합니다.

```python
from qmtl.sdk import Strategy, Node, StreamInput

class MyStrategy(Strategy):
    def setup(self):
        price = StreamInput(interval=60, period=30)

        def compute(view):
            return view

        out = Node(input=price, compute_fn=compute, name="out")
        self.add_nodes([price, out])

    def define_execution(self):
        self.set_target("out")
```

## 실행 모드

전략은 `Runner` 클래스로 실행합니다. 모드는 `backtest`, `dryrun`, `live`, `offline` 네 가지가 있으며 CLI 또는 Python 코드에서 선택할 수 있습니다.

```bash
# 커맨드라인 예시
python -m qmtl.sdk tests.sample_strategy:SampleStrategy --mode backtest --start-time 2024-01-01 --end-time 2024-02-01
python -m qmtl.sdk tests.sample_strategy:SampleStrategy --mode offline
```

```python
from qmtl.sdk import Runner
Runner.dryrun(MyStrategy)
```

## CLI 도움말

CLI에 대한 전체 옵션은 다음 명령으로 확인할 수 있습니다.

```bash
python -m qmtl.sdk --help
```

## 캐시 조회

`compute_fn`에는 `NodeCache.view()`가 반환하는 **읽기 전용 CacheView** 객체가
전달됩니다. 이전 버전에서 사용하던 `NodeCache.snapshot()`은 내부 구현으로
변경되었으므로 전략 코드에서 직접 호출하지 않아야 합니다.

## 백필 작업

노드 캐시를 과거 데이터로 초기화하는 방법은
[backfill.md](backfill.md) 문서를 참고하세요.

