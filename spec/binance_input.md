아래는 **qmtl‑strategies** 저장소에 Binance 데이터 스트림을 입력으로 받아 QuestDB에 기록하고 히스토리 재현을 지원하는 DAG 기능을 추가하기 위한 상세 구현 계획서입니다. QMTL의 DAG 구조, HistoryProvider/EventRecorder 인터페이스, 개발 가이드라인을 고려하여 작성했습니다.

---

## 1. 목표 및 개요

* **목적**: 실시간 Binance Kline/거래 데이터 스트림을 QMTL 전략에서 입력으로 받아, qmtl의 *history provider* 기능을 활용하여 QuestDB에 영속적으로 저장하고, 이후 백테스트/재현 시 해당 데이터를 로드할 수 있는 DAG(전략) 패키지를 추가한다.
* **핵심 요구사항**

  1. Binance 스트림을 `StreamInput`으로 받아 qmtl DAG에 연결한다.
  2. 히스토리 보존을 위해 `QuestDBLoader`/`QuestDBRecorder`를 사용한다. QuestDB는 node\_id와 interval별로 시계열을 저장하며, `fetch`, `coverage`, `fill_missing` 등을 통해 데이터 재현을 지원한다.
  3. 과거 데이터가 없을 경우 Binance API에서 캔들/틱 데이터를 가져오는 `BinanceFetcher`를 작성하거나 기존 예제를 재사용하여 QuestDB 테이블을 자동으로 보충한다.
  4. 전략이 DAGManager와 호환되도록 `Strategy` 기반으로 정의하고, `Runner`를 통해 backtest/dry-run/live 실행 모드를 지원한다.

---

## 2. 설계 및 세부 구현 방안

### 2.1 데이터 소스 및 히스토리 관리

1. **DataFetcher 구현**

   * `qmtl.docs/backfill.md`의 예제처럼, Binance REST API를 호출하여 지정 구간의 캔들(klines) 데이터를 `pandas.DataFrame`으로 반환하는 비동기형 `BinanceFetcher` 클래스를 구현한다.
   * 이미 `qmtl/examples/utils/binance_fetcher.py`에 간단한 구현이 있으므로 재사용하거나 확장한다.
   * DataFrame에는 `ts`(초 단위 timestamp)와 필요한 시세 열(`open`, `close`, `high`, `low`, `volume`)을 포함하도록 확장할 수 있다.

2. **HistoryProvider 구성**

   * `QuestDBLoader` 클래스는 QuestDB에서 노드 데이터를 조회하고, 연속된 timestamp 범위(coverage)를 반환하며, missing 데이터가 있을 경우 `fetcher`를 통해 채울 수 있다.
   * Loader를 초기화할 때 DSN(예: `postgresql://user:pass@localhost:8812/qdb`)과 `fetcher=BinanceFetcher()`를 전달하여 누락 데이터가 있을 때 Binance API로 자동 채워지도록 한다.

3. **EventRecorder 구성**

   * `QuestDBRecorder`는 스트림 입력에서 나온 이벤트(payload)를 QuestDB 테이블에 영속적으로 저장한다. `persist()` 메서드는 node\_id, interval, timestamp 및 payload를 삽입하는 SQL을 실행한다.
   * table 이름은 별도로 지정하지 않으면 스트림의 node\_id와 동일하게 된다.

### 2.2 DAG 및 전략 구성

1. **전략 패키지 생성**

   * `strategies/binance_history_strategy/` 디렉터리를 생성한다.
   * `__init__.py`에서 `Strategy`를 상속받은 클래스 `BinanceHistoryStrategy`를 구현한다.
   * 개발 가이드에 따라 QMTL 핵심 기능 수정은 피하고, 모든 전략 코드는 `strategies/` 디렉터리 아래에 위치시킨다.

2. **StreamInput 정의**

   * `setup()` 메서드에서 심볼마다 `StreamInput` 객체를 생성한다. 예를 들어 BTCUSDT 1분봉을 저장하려면:

     ```python
     from qmtl.sdk import StreamInput
     from qmtl.io import QuestDBLoader, QuestDBRecorder
     from strategies.utils.binance_fetcher import BinanceFetcher  # 새로 작성

     btc_stream = StreamInput(
         tags=["BTCUSDT", "binance", "price"],
         interval="60s",
         period=120,  # 히스토리 윈도우 크기 (분석 목적에 따라 조정)
         history_provider=QuestDBLoader(
             dsn="postgresql://user:pass@localhost:8812/qdb",
             fetcher=BinanceFetcher(),  # missing data 채우기용
         ),
         event_recorder=QuestDBRecorder(
             dsn="postgresql://user:pass@localhost:8812/qdb",
         ),
     )
     ```
   * `StreamInput`에 history\_provider와 event\_recorder를 지정하면 QMTL이 스트림과 QuestDB를 자동으로 연결하며, backfill 시 missing 데이터가 있으면 `fill_missing()`을 통해 fetcher가 호출된다.
   * 필요하다면 여러 심볼을 동시에 처리하도록 리스트로 관리한다(BTC, ETH 등).

3. **노드(계산) 추가**

   * 이 기능의 핵심 목표는 원본 데이터의 영속화이므로 반드시 복잡한 변환을 추가할 필요는 없다.
   * 그러나 DAG에 최소 하나의 downstream 노드를 추가해야 StreamInput의 출력이 다른 노드에 전달되어 DAG가 완성된다. 이를 위해 payload를 그대로 반환하는 identity 노드를 구현하거나, 간단한 지표(예: 이동평균)를 계산하는 노드를 추가할 수 있다.
   * 예:

     ```python
     from qmtl.sdk import Node

     def identity_fn(view):
         # view[btc_stream][60]에는 (timestamp, payload) 튜플들이 들어있다
         data = [v for _, v in view[btc_stream][60]]
         # 그대로 DataFrame으로 변환
         import pandas as pd
         return pd.DataFrame(data)

     identity_node = Node(input=btc_stream, compute_fn=identity_fn, name="btc_identity")
     ```
   * 위 노드는 실제 계산을 수행하지 않고 스트림 데이터를 그대로 내보내지만, `event_recorder` 덕분에 이미 QuestDB에 저장된다.

4. **DAG 연결**

   * `Strategy.add_nodes([btc_stream, identity_node])`를 호출하여 DAG에 노드들을 등록한다.
   * 여러 심볼을 처리한다면 각각의 stream과 identity 노드를 추가하여 DAG에 모두 연결한다.
   * DAGManager와 상호작용할 때 각 노드는 SHA-256 기반 deterministic ID를 가지므로 동일 코드/설정이면 재사용된다.

### 2.3 실행 및 백테스트

1. **실행 스크립트**

   * `strategies/strategy.py` 혹은 별도 스크립트에서 `Runner`를 사용해 전략을 실행한다. Backtest 시 시작/종료 timestamp를 제공하면 QMTL이 먼저 QuestDB로부터 히스토리를 로드하고 누락 데이터를 fetcher로 채운다.

     ```python
     from qmtl.sdk import Runner
     from strategies.binance_history_strategy import BinanceHistoryStrategy

     if __name__ == "__main__":
         # 백테스트 범위 설정
         Runner.backtest(
             BinanceHistoryStrategy,
             start_time=1700000000,  # 필요한 기간의 epoch timestamp
             end_time=1700003600,
             gateway_url="http://localhost:8000",  # 필요 시 Gateway 사용
         )
     ```
   * 실시간 스트리밍 모드에서는 `Runner.live()`를 사용할 수 있다. 이 경우 event\_recorder가 새로운 데이터가 도착할 때마다 QuestDB에 기록하며, history\_provider는 누락 데이터만 채운다.

2. **QuestDB 설정**

   * 프로젝트 루트 또는 `qmtl.yml`에 QuestDB DSN을 설정하고, 테스트 환경에서는 로컬 QuestDB를 사용한다.
   * 테이블 생성은 `QuestDBRecorder`가 자동으로 수행하지 않으므로, 테이블 스키마를 미리 정의하는 SQL을 제공하거나 초기화 스크립트를 작성한다. node\_id, interval, ts(타임스탬프) 및 payload 컬럼을 갖는 테이블을 만든다.

3. **로깅/모니터링**

   * QMTL의 metrics 서버를 활용하여 backfill 진행 상황(`backfill_jobs_in_progress`, `backfill_last_timestamp` 등)과 데이터 기록 현황을 모니터링한다.
   * Prometheus나 Grafana와 연동하여 모니터링 대시보드를 구축할 수 있다.

---

## 3. 구현 단계 (Task List)

| 단계                        | 내용                                                                                                                                                                                                               | 참고     |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| **1. 환경 준비**              | `git subtree pull --prefix=qmtl qmtl-subtree main`로 QMTL 서브트리를 최신화한다. QuestDB 로컬 인스턴스를 설치/실행하고 DSN을 확인한다. `uv pip install -e qmtl[dev]`로 의존성을 설치한다.                                                              | 개발 가이드 |
| **2. DataFetcher 작성**     | `strategies/utils/binance_fetcher.py`에 비동기 `BinanceFetcher` 클래스를 구현하거나 기존 예제를 가져와 필요한 속성(심볼, interval 등)을 일반화한다.                                                                                                 |        |
| **3. 전략 패키지 생성**          | `strategies/binance_history_strategy/__init__.py`에 `BinanceHistoryStrategy` 클래스를 정의한다. `setup()`에서 StreamInput과 노드를 구성한다.                                                                                        |        |
| **4. StreamInput 구성**     | 심볼마다 `StreamInput`을 생성하고, `history_provider=QuestDBLoader(dsn, fetcher=BinanceFetcher())`, `event_recorder=QuestDBRecorder(dsn)`을 지정한다. period와 interval은 요구에 맞게 설정한다.                                           |        |
| **5. 노드 및 DAG 구성**        | identity 노드 또는 간단한 지표 노드를 정의하고 모든 노드를 `self.add_nodes()`로 등록하여 DAG를 완성한다.                                                                                                                                        |        |
| **6. 실행 스크립트 작성**         | `strategies/strategy.py`를 수정하거나 별도 스크립트를 만들어 `Runner.backtest/live/dryrun`으로 전략을 실행할 수 있게 한다. start/end timestamp를 입력받아 backfill을 진행한다.                                                                          |        |
| **7. QuestDB 테이블 스키마 정의** | `create_table.sql`과 같은 초기화 스크립트를 작성하여 `node_id VARCHAR`, `interval INT`, `ts TIMESTAMP`, 시가/종가 등 payload 컬럼을 포함한 테이블을 생성한다.                                                                                      |        |
| **8. 테스트 작성**             | `tests/test_binance_history_strategy.py`를 작성하여 다음을 검증한다: (a) StreamInput 생성 시 QuestDBLoader/Recorder가 제대로 바인딩되는지, (b) 백테스트 실행 후 QuestDB 테이블에 데이터가 저장되는지, (c) history\_provider.fetch()가 QuestDB에서 데이터를 읽을 수 있는지. |        |
| **9. 문서 업데이트**            | `strategies/README.md`에 새 전략 사용법을 추가하고, 새로운 DAG가 하는 일을 설명한다. 필요 시 `docs/alphadocs/`에 알파 전략 문서를 작성하여 레지스트리 업데이트를 수행한다.                                                                                            |        |
| **10. 리뷰 및 병합**           | PR 작성 시 QMTL 서브트리 상태를 확인하고, 모든 테스트를 통과한 후 병합한다.                                                                                                                                                                  |        |

---

## 4. 고려 사항 및 확장

* **다중 심볼/다중 주기 지원**: BTCUSDT 뿐 아니라 ETHUSDT 등 여러 자산을 병렬로 저장하려면 StreamInput을 여러 개 생성하고 동일한 BinanceFetcher 인스턴스를 공유할 수 있다. interval 값(예: 1m, 5m)을 다양하게 설정할 수 있다.
* **WebSocket 스트림**: 향후 실시간 거래량/틱 데이터를 처리하려면 Binance WebSocket 클라이언트를 구현하여 QMTL Gateway를 통해 토픽에 publish하고 DAG에서 소비하도록 확장할 수 있다.
* **압축·파티션 관리**: QuestDB는 시계열 DB 특성상 파티셔닝을 지원한다. 테이블을 월 또는 일 단위로 파티셔닝하여 백테스트 시 읽기 효율을 높이는 방안을 고려한다.
* **에러 처리**: `BinanceFetcher` 호출 시 네트워크 오류나 API 제한으로 실패할 수 있으므로 재시도와 rate-limit 처리를 구현한다. QMTL의 backfill 엔진은 실패시 재시도 카운터를 노출하므로 모니터링을 통해 감지한다.

---

이 계획에 따라 구현하면 Binance 실시간 데이터 스트림을 QMTL 전략 DAG를 통해 QuestDB에 저장하고, 이후 백테스트나 분석에서 동일 데이터를 재현할 수 있는 기능을 추가할 수 있습니다.
