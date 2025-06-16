# SDK 사용 가이드

본 문서는 QMTL SDK를 이용해 전략을 구현하고 실행하는 기본 절차를 소개합니다. 보다 상세한 아키텍처 설명과 예시는 `architecture.md`와 `examples/` 디렉터리를 참고하세요.

## 설치

```bash
uv venv
uv pip install -e .[dev]
```

필요에 따라 선택적 확장 패키지를 설치할 수 있습니다.

```bash
uv pip install -e .[indicators]  # 기술 지표 노드 모음
uv pip install -e .[io]         # 데이터 IO 모듈
uv pip install -e .[generators]  # 시뮬레이션 데이터 생성기
```

## 기본 구조


SDK를 사용하려면 `Strategy` 클래스를 상속하고 `setup()` 메서드만 구현하면 됩니다. 노드는 `StreamInput`, `TagQueryNode` 와 같은 **소스 노드**(`SourceNode`)와 다른 노드를 처리하는 **프로세싱 노드**(`ProcessingNode`)로 나뉩니다. `ProcessingNode`는 하나 이상의 업스트림을 반드시 가져야 합니다. `interval`과 `period` 값은 정수 또는 `"1h"`, `"30m"`, `"45s"`처럼 단위 접미사를 가진 문자열로 지정할 수 있습니다. `TagQueryNode` 자체는 네트워크 요청을 수행하지 않고, Runner가 생성하는 **TagQueryManager**가 Gateway와 통신하여 큐 목록을 갱신합니다.


```python
from qmtl.sdk import Strategy, ProcessingNode, StreamInput

class MyStrategy(Strategy):
    def setup(self):
        price = StreamInput(interval="1m", period=30)

        def compute(view):
            return view

        out = ProcessingNode(input=price, compute_fn=compute, name="out")
        self.add_nodes([price, out])
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

`Runner`를 사용하면 각 `TagQueryNode`가 등록된 후 자동으로 Gateway와 통신하여
해당 태그에 매칭되는 큐를 조회하고 WebSocket 구독을 시작합니다.

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

