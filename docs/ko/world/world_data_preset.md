---
title: "월드 데이터 preset 계약"
tags: [world, data, seamless]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 월드 데이터 preset 계약

본 문서는 월드가 데이터 플레인 계약의 SSOT라는 점을 전제로, data preset과 Tag/queue 라우팅 규약을 정리합니다. Seamless 구현 자체는 [심리스 데이터 프로바이더 v2](../architecture/seamless_data_provider_v2.md), 그래프/큐 해석은 [DAG Manager](../architecture/dag-manager.md)를 참조합니다.

<a id="62-데이터-preset-onramp"></a>
## 1. 데이터 preset on-ramp

T3 P0-M1 목표는 world + data preset만으로 Runner/CLI가 적절한 Seamless 인스턴스를 자동 구성하고 `StreamInput.history_provider`에 주입하는 것입니다.

### 1.1 계약

1. 월드는 `data.presets[]`를 반드시 포함하는 데이터 플레인 SSOT입니다.
2. `data.presets[].preset`은 Seamless data preset ID이며, 저장소/백필/라이브/스키마/SLA 구현은 Seamless preset 맵에 정의합니다.
3. Runner/CLI 기본값은 첫 번째 preset이며, `--data-preset <id>` override는 월드에 선언된 ID로만 제한합니다.
4. preset이 가리키는 구성 요소가 없으면 즉시 실패하며, 레거시 provider로 조용히 폴백하지 않습니다.

### 1.2 스키마 예시

```yaml
world:
  id: "crypto-mom-1h"
  data:
    presets:
      - id: "ohlcv-1m"
        preset: "ohlcv.binance.spot.1m"
        universe:
          symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
          asset_class: "crypto"
          venue: "binance"
        window:
          warmup_bars: 1440
          min_history: "90d"
          backfill_start: "2024-01-01T00:00:00Z"
        seamless:
          sla_preset: "baseline"
          conformance_preset: "strict-blocking"
          backfill_mode: "background"
          stabilization_bars: 2
          publish_fingerprint: true
        live:
          max_lag: "45s"
          allow_partial: false
```

### 1.3 필드 해석

- `id`: 월드 내부에서 참조되는 데이터셋 키.
- `preset`: Seamless data preset 키. `family.source.market.interval` 형태를 권장합니다.
- `universe`: 기본 심볼/태그 질의. 전략 입력이 더 구체적이면 그 입력이 우선합니다.
- `window`: warmup과 최소 히스토리 요구사항. world의 `data_currency`와 일치해야 합니다.
- `seamless`: SLA, conformance, backfill 세부 옵션.
- `live`: 라이브 지연 허용 한도와 부분 허용 정책.

### 1.4 표준 preset 매핑

| preset ID | 저장소/백필 | 라이브 피드 | 기본 SLA/Conformance | 용도 |
| --- | --- | --- | --- | --- |
| `ohlcv.binance.spot.1m` | QuestDB + CCXT(Binance) 백필 | Binance WS `kline@1m` | `baseline` / `strict-blocking` | 크립토 1분 모멘텀 |
| `ohlcv.polygon.us_equity.1d` | QuestDB + Polygon REST 백필 | 없음 | `tolerant-partial` / `strict-blocking` | 미국 주식 EOD |
| `ohlcv.nautilus.crypto.1m` | Nautilus DataCatalog | 없음 | `baseline` / `strict-blocking` | 연구/백테스트 |
| `ohlcv.nautilus.binance.1m` | Nautilus DataCatalog | CCXT Pro WS | `baseline` / `strict-blocking` | 히스토리컬 + 라이브 |
| `ohlcv.nautilus.binance.1h` | Nautilus DataCatalog | CCXT Pro WS | `baseline` / `strict-blocking` | 1시간 바 히스토리컬 + 라이브 |

### 1.5 Nautilus 참고사항

- `nautilus.catalog`: 히스토리컬 전용입니다.
- `nautilus.full`: 히스토리컬(Nautilus) + 라이브(CCXT Pro) 조합입니다.
- `nautilus_trader` 미설치 시 `NautilusPresetUnavailableError`를 발생시켜야 합니다.

### 1.6 계약 테스트 훅

- `tests/e2e/core_loop/worlds/core-loop-demo.yml`에 world data preset 예시를 유지합니다.
- 기대값:
  - world에 preset이 없으면 Runner/CLI는 실패합니다.
  - preset이 있으면 Gateway/WorldService 스텁이 해당 preset ID를 반환하고 Runner가 Seamless preset을 구성합니다.

## 2. Tag/interval ↔ 큐 네임스페이스 규약

멀티 업스트림/멀티자산 전략에서 TagQueryNode가 적절한 큐를 자동 선택하려면, DAG Manager, Gateway, Seamless가 동일한 태그/interval/namespace 규약을 공유해야 합니다.

### 2.1 태그

- ComputeNode/Queue는 자산군, venue, 데이터 패밀리 등을 표현하는 태그 목록을 가집니다.
- TagQueryNode와 TagQueryManager는 태그 집합과 interval을 기준으로 Gateway `GET /queues/by_tag`를 호출합니다.

### 2.2 interval

- `GET /queues/by_tag`의 `interval`은 초 단위 큐 interval이며 노드/큐 설정값과 정확히 일치해야 합니다.
- world preset의 `interval_ms` 값도 동일한 간격 규약을 유지해야 합니다.

### 2.3 네임스페이스

- topic namespace가 활성화되면 Gateway는 `{world_id}.{execution_domain}.<topic>` 프리픽스를 적용할 수 있습니다.
- 동일 태그/interval이라도 world 또는 execution domain이 다르면 큐 집합은 분리되어야 합니다.

### 2.4 Seamless와의 관계

- Seamless preset은 어떤 데이터 소스로 큐를 채울지 결정합니다.
- TagQuery는 이미 존재하는 큐 중 어떤 큐를 읽을지 결정합니다.
- 따라서 world preset의 `universe`/`interval_ms`, DAG Manager 태그·interval, Gateway `/queues/by_tag` 규약은 함께 진화해야 합니다.

{{ nav_links() }}
