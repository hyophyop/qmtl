---
title: "Nautilus Trader Catalog 통합 가이드"
date: 2026-01-08
tags:
  - integration
  - nautilus
  - data
  - catalog
---

# Nautilus Trader Data Catalog 통합 가이드

QMTL의 Seamless Data Provider를 통해 Nautilus Trader의 Data Catalog에 저장된 데이터를 투명하게 읽을 수 있습니다.

## 개요

Nautilus Trader는 고성능 알고리즘 트레이딩 프레임워크로, Parquet 기반의 효율적인 Data Catalog를 제공합니다. QMTL의 `NautilusCatalogDataSource` 어댑터를 사용하면:

- Nautilus로 수집/저장된 OHLCV bars, ticks, quotes를 QMTL 전략에서 바로 사용 가능
- 타임스탬프 변환(나노초 ↔ 초) 자동 처리
- 스키마 정규화(Decimal → float64, 컬럼명 매핑) 자동 처리
- Coverage 캐싱으로 빠른 데이터 조회

## 설치

### 1. Nautilus Trader 의존성 설치

```bash
uv pip install qmtl[nautilus]
```

이 명령은 `nautilus_trader>=1.200.0`을 자동으로 설치합니다.

### 2. Nautilus Catalog 준비

Nautilus Trader를 사용해 데이터를 수집하고 catalog에 저장합니다:

```python
from nautilus_trader.persistence.catalog import DataCatalog

# Catalog 생성
catalog = DataCatalog("~/.nautilus/catalog")

# 데이터 저장 (Nautilus 워크플로 사용)
# ... Nautilus로 데이터 수집 및 저장 ...
```

자세한 내용은 [Nautilus Trader 공식 문서](https://nautilustrader.io/docs/latest/concepts/data.html)를 참조하세요.

## 기본 사용법

### OHLCV Bars 읽기

```python
from pathlib import Path
from nautilus_trader.persistence.catalog import DataCatalog
from qmtl.runtime.io.nautilus_catalog_source import NautilusCatalogDataSource
from qmtl.runtime.sdk.seamless_data_provider import (
    SeamlessDataProvider,
    DataAvailabilityStrategy,
)

# 1. Nautilus catalog 로드
catalog_path = Path("~/.nautilus/catalog").expanduser()
catalog = DataCatalog(str(catalog_path))

# 2. QMTL 어댑터 생성
nautilus_source = NautilusCatalogDataSource(
    catalog=catalog,
    coverage_cache_ttl=3600,  # Coverage 캐시 1시간
)

# 3. Seamless provider에 통합
provider = SeamlessDataProvider(
    strategy=DataAvailabilityStrategy.SEAMLESS,
    storage_source=nautilus_source,
)

# 4. 데이터 조회
bars = await provider.fetch(
    start=1700000000,  # Unix timestamp (초)
    end=1700003600,
    node_id="ohlcv:binance:BTC/USDT:1m",
    interval=60,
)

print(f"Retrieved {len(bars)} bars")
print(bars.head())
```

### Trade Ticks 읽기

```python
# Tick 데이터 조회
ticks = await provider.fetch(
    start=1700000000,
    end=1700001000,
    node_id="tick:binance:BTC/USDT",
    interval=1,
)

# 결과 스키마
# - ts: int64 (Unix 초)
# - price: float64
# - size: float64
# - side: str ('buy' 또는 'sell')
```

### Quote Ticks 읽기

```python
# Quote 데이터 조회
quotes = await provider.fetch(
    start=1700000000,
    end=1700001000,
    node_id="quote:binance:BTC/USDT",
    interval=1,
)

# 결과 스키마
# - ts: int64 (Unix 초)
# - bid: float64
# - ask: float64
# - bid_size: float64
# - ask_size: float64
```

## node_id 매핑 규칙

QMTL과 Nautilus의 식별자 매핑 규칙:

| 데이터 타입 | QMTL node_id | Nautilus 식별자 |
|-------------|--------------|-----------------|
| OHLCV bars | `ohlcv:{venue}:{instrument}:{timeframe}` | `(venue, instrument, bar_type)` |
| Trade ticks | `tick:{venue}:{instrument}` | `(venue, instrument)` |
| Quote ticks | `quote:{venue}:{instrument}` | `(venue, instrument)` |

### 예시

```python
# OHLCV
"ohlcv:binance:BTC/USDT:1m" → catalog.read_bars(
    instrument="BTC/USDT",
    bar_type="BTC/USDT-1m-LAST",
)

# Ticks
"tick:binance:BTC/USDT" → catalog.read_ticks(
    instrument="BTC/USDT",
)

# Quotes
"quote:binance:BTC/USDT" → catalog.read_quotes(
    instrument="BTC/USDT",
)
```

## 전략 통합

Nautilus 데이터를 QMTL 전략에서 사용:

```python
from qmtl.runtime.sdk import Strategy, StreamInput

class MyBacktestStrategy(Strategy):
    def setup(self):
        # Nautilus catalog를 history provider로 사용
        self.price = StreamInput(
            tags=["btc", "spot"],
            interval="60s",
            period=100,
            history_provider=provider,  # Nautilus-backed provider
            node_id_override="ohlcv:binance:BTC/USDT:1m",
        )
        
        def compute(view):
            # 최근 10개 바 조회
            bars = view[self.price][10]
            if not bars.empty:
                close_price = bars['close'].iloc[-1]
                # ... 전략 로직 ...
        
        self.compute = compute
```

## 타임스탬프 변환

Nautilus는 나노초 단위, QMTL은 초 단위를 사용합니다. 어댑터가 자동으로 변환합니다:

```python
# Nautilus (나노초)
nautilus_ts = 1700000000 * 1_000_000_000  # 1,700,000,000,000,000,000

# QMTL (초)
qmtl_ts = 1700000000

# 변환
qmtl_ts = nautilus_ts // 1_000_000_000
```

어댑터가 자동으로 처리하므로, 사용자는 QMTL 컨벤션(Unix 초)만 사용하면 됩니다.

## 스키마 정규화

### OHLCV Bars

**Nautilus 원본**:
```python
{
    'ts_event': int64,  # nanoseconds
    'open': Decimal,
    'high': Decimal,
    'low': Decimal,
    'close': Decimal,
    'volume': Decimal
}
```

**QMTL 정규화 후**:
```python
{
    'ts': int64,      # seconds
    'open': float64,
    'high': float64,
    'low': float64,
    'close': float64,
    'volume': float64
}
```

### Trade Ticks

**Nautilus 원본**:
```python
{
    'ts_event': int64,
    'price': Decimal,
    'size': Decimal,
    'aggressor_side': str  # 'BUY' or 'SELL'
}
```

**QMTL 정규화 후**:
```python
{
    'ts': int64,
    'price': float64,
    'size': float64,
    'side': str  # 'buy' or 'sell'
}
```

### Quote Ticks

**Nautilus 원본**:
```python
{
    'ts_event': int64,
    'bid_price': Decimal,
    'ask_price': Decimal,
    'bid_size': Decimal,
    'ask_size': Decimal
}
```

**QMTL 정규화 후**:
```python
{
    'ts': int64,
    'bid': float64,
    'ask': float64,
    'bid_size': float64,
    'ask_size': float64
}
```

## Coverage 조회

데이터 가용성 확인:

```python
# Coverage 조회
coverage = await nautilus_source.coverage(
    node_id="ohlcv:binance:BTC/USDT:1m",
    interval=60,
)

# 결과: [(start_ts, end_ts), ...]
for start, end in coverage:
    print(f"Available: {start} - {end}")

# 특정 구간 가용성 체크
is_available = await nautilus_source.is_available(
    start=1700000000,
    end=1700003600,
    node_id="ohlcv:binance:BTC/USDT:1m",
    interval=60,
)

print(f"Data available: {is_available}")
```

## 설정 옵션

### Coverage 캐시 TTL

```python
nautilus_source = NautilusCatalogDataSource(
    catalog=catalog,
    coverage_cache_ttl=3600,  # 초 단위 (기본: 3600 = 1시간)
)
```

Coverage 조회는 파일 시스템 스캔이 필요할 수 있어 느립니다. TTL을 설정해 결과를 캐싱합니다.

### 데이터 소스 우선순위

```python
from qmtl.runtime.sdk.seamless_data_provider import DataSourcePriority

nautilus_source = NautilusCatalogDataSource(
    catalog=catalog,
    priority=DataSourcePriority.STORAGE,  # 기본값
)
```

Seamless provider가 여러 소스를 조율할 때 우선순위를 결정합니다.

## 성능 최적화

### Coverage 인덱스 사전 생성 (구현 완료)

대규모 catalog의 경우, coverage 인덱스를 미리 생성하면 조회 속도가 크게 향상됩니다:

```python
from qmtl.runtime.io.nautilus_coverage_index import NautilusCoverageIndex

# 인덱스 생성 (한 번만 실행)
coverage_index = NautilusCoverageIndex(
    catalog_path=Path("~/.nautilus/catalog"),
    index_path=Path("~/.qmtl/nautilus_coverage.json"),
)
await coverage_index.build_index()

# 이후 빠른 coverage 조회
coverage = coverage_index.get_coverage(
    node_id="ohlcv:binance:BTC/USDT:1m",
    interval=60,
)
```

인덱스 빌드는 최초 한 번만 실행하면 되며, 이후 조회는 매우 빠릅니다(수 μs).

### Conformance 규칙 적용

Tick/Quote 데이터 품질 검증:

```python
from qmtl.runtime.sdk.conformance import (
    TickConformanceRule,
    QuoteConformanceRule,
)

# Tick 검증
tick_rule = TickConformanceRule()
report = tick_rule.validate(ticks_df)

if report.warnings:
    print(f"Tick data warnings: {report.warnings}")
    print(f"Issues: {report.flags_counts}")

# Quote 검증
quote_rule = QuoteConformanceRule()
report = quote_rule.validate(quotes_df)

if report.warnings:
    print(f"Quote data warnings: {report.warnings}")
```

### 성능 벤치마크

통합 성능을 측정하려면:

```bash
uv run python scripts/benchmark_nautilus_integration.py --catalog ~/.nautilus/catalog
```

벤치마크는 다음을 측정합니다:
- Coverage 인덱스 빌드 시간
- Coverage 조회 성능 (인덱스 유/무)
- 데이터 fetch 처리량
- 스키마 변환 오버헤드
- Conformance 검증 시간

### 병렬 조회

여러 종목 동시 조회:

```python
import asyncio

async def fetch_multiple():
    tasks = [
        provider.fetch(start, end, node_id="ohlcv:binance:BTC/USDT:1m", interval=60),
        provider.fetch(start, end, node_id="ohlcv:binance:ETH/USDT:1m", interval=60),
        provider.fetch(start, end, node_id="ohlcv:binance:SOL/USDT:1m", interval=60),
    ]
    results = await asyncio.gather(*tasks)
    return results

bars_list = await fetch_multiple()
```

## 문제 해결

### ImportError: nautilus_trader is required

```bash
# 해결: Nautilus 의존성 설치
uv pip install qmtl[nautilus]
```

### Catalog not found

```python
catalog_path = Path("~/.nautilus/catalog").expanduser()
if not catalog_path.exists():
    print("Catalog not found. Create it first using Nautilus Trader.")
```

Nautilus Trader를 사용해 먼저 catalog를 생성하고 데이터를 저장해야 합니다.

### 빈 결과 반환

```python
# Coverage 확인
coverage = await nautilus_source.coverage(
    node_id="ohlcv:binance:BTC/USDT:1m",
    interval=60,
)
if not coverage:
    print("No data available for this instrument")

# Catalog에 저장된 종목 리스트 확인
instruments = catalog.instruments(venue="binance")
for inst in instruments:
    print(inst.id)
```

### 타임스탬프 불일치

QMTL은 Unix 초, Nautilus는 나노초를 사용합니다. 어댑터가 자동 변환하지만, 직접 catalog를 조회할 경우 주의:

```python
# QMTL 방식 (권장)
bars = await provider.fetch(
    start=1700000000,  # 초
    end=1700003600,
    node_id="ohlcv:binance:BTC/USDT:1m",
    interval=60,
)

# 직접 Nautilus 조회 (비권장)
bars = catalog.read_bars(
    instrument="BTC/USDT",
    bar_type="BTC/USDT-1m-LAST",
    start=1700000000 * 1_000_000_000,  # 나노초로 변환 필요!
    end=1700003600 * 1_000_000_000,
)
```

## 예제 코드

전체 예제는 {{ code_link('examples/nautilus_catalog_example.py') }}를 참조하세요:

```bash
# 예제 실행
uv run python examples/nautilus_catalog_example.py
```

## 히스토리컬 + 라이브 통합 (Seamless Full)

Nautilus DataCatalog(히스토리컬)와 CCXT Pro(라이브)를 함께 사용하면 진정한 Seamless 데이터 제공이 가능합니다.

### 아키텍처

```
┌─────────────────────────────────────────┐
│         SeamlessDataProvider            │
├─────────────────┬───────────────────────┤
│ Historical      │ Live                  │
│ (Nautilus)      │ (CCXT Pro)            │
│   DataCatalog   │   WebSocket           │
│   Parquet Files │   Real-time Stream    │
└────────┬────────┴───────────┬───────────┘
         │                    │
     read_bars()         watch_ohlcv()
```

### nautilus.full 프리셋 사용

```python
from qmtl.runtime.sdk.seamless import SeamlessBuilder

# 가장 간단한 방법: 프리셋 사용
builder = SeamlessBuilder()
builder = builder.apply_preset("nautilus.full", {
    "catalog_path": "~/.nautilus/catalog",
    "exchange_id": "binance",
    "symbols": ["BTC/USDT", "ETH/USDT"],
    "timeframe": "1m",
})

assembly = builder.build()
provider = assembly.provider

# Historical 데이터 조회
hist_bars = await provider.fetch(
    start=1700000000,
    end=1700003600,
    node_id="ohlcv:binance:BTC/USDT:1m",
    interval=60,
)

# Live 스트리밍
async for ts, bars in provider.stream(
    node_id="ohlcv:binance:BTC/USDT:1m",
    interval=60,
):
    print(f"[{ts}] Received {len(bars)} bars")
```

### 수동 구성

프리셋 대신 직접 구성할 수도 있습니다:

```python
from nautilus_trader.persistence.catalog import DataCatalog
from qmtl.runtime.io import (
    NautilusCatalogDataSource,
    CcxtProConfig,
    CcxtProLiveFeed,
)
from qmtl.runtime.sdk.seamless_data_provider import SeamlessDataProvider

# 1. Historical: Nautilus DataCatalog
catalog = DataCatalog("~/.nautilus/catalog")
storage = NautilusCatalogDataSource(catalog=catalog)

# 2. Live: CCXT Pro WebSocket
live_config = CcxtProConfig(
    exchange_id="binance",
    symbols=["BTC/USDT"],
    timeframe="1m",
    mode="ohlcv",
    emit_building_candle=False,  # 완성된 바만 emit
)
live_feed = CcxtProLiveFeed(live_config)

# 3. Seamless Provider 통합
provider = SeamlessDataProvider(
    storage_source=storage,
    live_feed=live_feed,
)
```

### 사용 가능한 프리셋

| 프리셋 | 설명 | 구성요소 |
|--------|------|----------|
| `nautilus.catalog` | 히스토리컬 데이터만 | NautilusCatalogDataSource |
| `nautilus.full` | 히스토리컬 + 라이브 | NautilusCatalogDataSource + CcxtProLiveFeed |

### 프리셋 설정 옵션

#### nautilus.catalog

| 옵션 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `catalog_path` | str | `~/.nautilus/catalog` | Nautilus catalog 경로 |
| `priority` | str | `STORAGE` | DataSourcePriority |

#### nautilus.full

| 옵션 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `catalog_path` | str | `~/.nautilus/catalog` | Nautilus catalog 경로 |
| `exchange_id` | str | **필수** | 거래소 ID (예: "binance") |
| `symbols` | list[str] | `[]` | 심볼 리스트 |
| `timeframe` | str | `"1m"` | OHLCV 타임프레임 |
| `mode` | str | `"ohlcv"` | `"ohlcv"` 또는 `"trades"` |
| `sandbox` | bool | `False` | 샌드박스 모드 |

### 라이브 데이터 고려사항

1. **거래소 지원**: CCXT Pro가 지원하는 거래소여야 함 ([CCXT Pro 지원 거래소](https://docs.ccxt.com/en/latest/ccxt.pro.manual.html#exchanges))

2. **API 키**: 일부 거래소는 WebSocket 연결에 API 키 필요
   ```python
   live_config = CcxtProConfig(
       exchange_id="binance",
       symbols=["BTC/USDT"],
       timeframe="1m",
       # API 키는 환경변수로 설정
       # BINANCE_API_KEY, BINANCE_SECRET
   )
   ```

3. **Rate Limiting**: CCXT Pro가 자동으로 관리하지만, 많은 심볼 구독 시 주의

4. **재연결**: 네트워크 오류 시 자동 재연결 (exponential backoff)

## 관련 문서

- [Nautilus Trader Data Catalog 통합 설계](../design/nautilus_catalog_integration.md)
- [QMTL Seamless Data Provider](ccxt_seamless_usage.md)
- [Nautilus Trader 공식 문서](https://nautilustrader.io/)
