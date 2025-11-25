---
title: "레이어 기반 템플릿 시스템 퀵스타트"
tags:
  - guide
  - templates
  - layers
  - quickstart
author: "QMTL Team"
last_modified: 2025-10-18
---

{{ nav_links() }}

# 레이어 기반 템플릿 시스템 퀵스타트

이 가이드는 QMTL의 새로운 레이어 기반 템플릿 시스템을 빠르게 시작하는 방법을 설명합니다.

## 개요

레이어 기반 시스템을 사용하면 전략의 각 단계(데이터 공급, 신호 생성, 실행, 브로커리지)를 독립적으로 구성하고 조합할 수 있습니다.

### 사용 가능한 레이어

| 레이어 | 설명 | 의존성 |
|--------|------|--------|
| **data** | 데이터 공급 및 수집 | 없음 |
| **signal** | 알파 생성 및 신호 변환 | data |
| **execution** | 주문 실행 및 관리 | signal |
| **brokerage** | 거래소 통합 | execution |
| **monitoring** | 관측 및 메트릭 수집 | 없음 |

### 사용 가능한 프리셋

| 프리셋 | 레이어 | 용도 |
|--------|--------|------|
| **minimal** | data, signal | 백테스팅, 연구 |
| **research** | data, signal, monitoring | 알파 연구 및 분석 |
| **production** | data, signal, execution, brokerage, monitoring | 실전 트레이딩 |
| **execution** | execution, brokerage | 외부 신호 기반 실행 |

---

## 빠른 시작

### 1. 프리셋으로 프로젝트 생성

```bash
# 사용 가능한 프리셋 확인
qmtl project list-presets

# 최소 구성으로 프로젝트 생성
qmtl project init --path my_strategy --preset minimal

# 프로덕션 구성으로 프로젝트 생성
qmtl project init --path my_prod --preset production
```

### 2. 생성된 프로젝트 구조

```
my_strategy/
├── .gitignore              # Git 제외 파일
├── qmtl.yml                # QMTL 설정
├── strategy.py             # 전략 진입점
├── layers/                 # 레이어 디렉토리
│   ├── __init__.py
│   ├── data/               # 데이터 레이어
│   │   ├── __init__.py
│   │   ├── providers.py    # 데이터 제공자 export
│   │   └── stream_input.py # StreamInput 구현
│   └── signal/             # 신호 레이어
│       ├── __init__.py
│       ├── strategy.py     # 전략 export
│       └── single_indicator.py  # 단일 지표 전략
└── tests/                  # 테스트 디렉토리
    └── test_strategy.py
```

### 3. 레이어 추가

기존 프로젝트에 레이어를 추가할 수 있습니다.

```bash
cd my_strategy

# 모니터링 레이어 추가
qmtl project layer add monitoring

# 실행 레이어 추가 (signal 레이어 필요)
qmtl project layer add execution
```

### 4. 레이어 메타데이터와 구조 검증

```bash
# 사용 가능한 레이어와 템플릿 확인
qmtl project layer list --show-templates

# 프로젝트 구조 검증
qmtl project layer validate --path my_strategy
```

---

## 레이어별 상세 가이드

### Data 레이어

데이터 공급을 담당합니다.

**템플릿:**
- `stream_input.py`: 기본 StreamInput
- `ccxt_provider.py`: CCXT 데이터 제공자

**사용 예시:**

```python
# layers/data/providers.py에서 import
from layers.data.providers import get_data_provider

# 데이터 스트림 생성
data_stream = get_data_provider()
```

**커스터마이징:**

```python
# layers/data/custom_provider.py
from qmtl.runtime.sdk import StreamInput

def create_custom_stream():
    return StreamInput(
        interval="60s",
        period=50,
        name="custom_stream",
    )
```

### Signal 레이어

신호 생성을 담당합니다.

**템플릿:**
- `single_indicator.py`: 단일 지표 전략
- `multi_indicator.py`: 복수 지표 전략

**사용 예시:**

```python
# layers/signal/strategy.py에서 import
from layers.signal.strategy import create_strategy

# 전략 생성
strategy = create_strategy()
```

**커스터마이징:**

원하는 지표와 로직을 추가하려면 signal 레이어 템플릿을 수정하세요.

```python
# layers/signal/my_strategy.py
from qmtl.runtime.sdk import Strategy, Node
from qmtl.runtime.indicators import ema, rsi

class MyStrategy(Strategy):
    def setup(self):
        from layers.data.providers import get_data_provider

        price = get_data_provider()
        ema_node = ema(price, period=20)
        rsi_node = rsi(price, period=14)

        # 커스텀 신호 로직
        def my_signal(view):
            # ... 신호 생성 로직
            pass

        signal = Node(input=[ema_node, rsi_node], compute_fn=my_signal)
        self.add_nodes([price, ema_node, rsi_node, signal])
```

### Execution 레이어

주문 실행을 담당합니다.

**템플릿:**
- `nodeset.py`: NodeSet 기반 실행 파이프라인

**사용 예시:**

```python
from layers.execution.nodeset import attach_execution_to_strategy

# 전략에 실행 레이어 연결
attach_execution_to_strategy(strategy, signal_node)
```

### Brokerage 레이어

거래소 통합을 담당합니다.

**템플릿:**
- `ccxt_binance.py`: Binance 통합

**사용 예시:**

```python
from layers.brokerage.ccxt_binance import create_broker

# 브로커 생성 (testnet)
broker = create_broker(testnet=True)

# 주문 실행
broker.place_order(
    symbol="BTC/USDT",
    side="buy",
    amount=0.001,
)
```

### Monitoring 레이어

메트릭 수집을 담당합니다.

**템플릿:**
- `metrics.py`: 기본 메트릭 수집

**사용 예시:**

```python
from layers.monitoring.metrics import get_metrics_collector

collector = get_metrics_collector()

# 신호 기록
collector.record_signal("BUY", strength=0.8)

# 거래 기록
collector.record_trade("BTC/USDT", "buy", 0.001, 50000)

# 성과 기록
collector.record_performance("sharpe_ratio", 1.5)

# 메트릭 조회
metrics = collector.get_metrics()
```

---

## 고급 사용법

### 1. 레이어 직접 선택

프리셋 대신 레이어를 직접 선택할 수 있습니다.

```bash
# 데이터와 신호만
qmtl project init --path my_custom --layers data,signal

# 의존성 자동 해결 (execution 선택 시 data, signal 자동 포함)
qmtl project init --path my_exec --layers execution
```

### 2. 사용 가능한 레이어 확인

```bash
qmtl project layer list
```

### 3. 프로젝트 검증

프로젝트 구조가 올바른지 검증합니다.

```bash
qmtl project layer validate
```

---

## 전략 실행

생성된 프로젝트의 `strategy.py`를 실행합니다.

```bash
cd my_strategy

# 오프라인 모드 (Gateway 불필요)
python strategy.py

# 프로덕션 모드 (Gateway 필요)
# strategy.py에서 Runner.run() 사용하도록 수정 후:
python strategy.py
```

---

## 문제 해결

### Import 에러

레이어 간 import가 실패하면 PYTHONPATH를 설정하세요.

```bash
export PYTHONPATH=/path/to/my_strategy:$PYTHONPATH
python strategy.py
```

### 레이어 의존성 에러

레이어 추가 시 의존성 에러가 발생하면 필요한 레이어를 먼저 추가하세요.

```bash
# EXECUTION은 SIGNAL을 요구
qmtl project layer add signal  # 먼저 추가
qmtl project layer add execution  # 그 다음 추가
```

### 템플릿 파일 수정

생성된 템플릿 파일은 자유롭게 수정해 프로젝트에 맞게 커스터마이징하세요.

---

## 다음 단계

- [레이어 템플릿 시스템 아키텍처](../architecture/layered_template_system.md)에서 상세 설계를 확인하세요.
- [전략 개발 워크플로](strategy_workflow.md)에서 전체 프로세스를 학습하세요.
- [SDK 튜토리얼](sdk_tutorial.md)에서 SDK 사용법을 익히세요.

---

## 참고 자료

- [Architecture Overview](../architecture/README.md)
- [Layered Template System Architecture](../architecture/layered_template_system.md)
- [Exchange Node Sets](../architecture/exchange_node_sets.md)
- [SDK Tutorial](sdk_tutorial.md)

---

**문서 버전**: 1.0
**최종 검토**: 2025-10-18
