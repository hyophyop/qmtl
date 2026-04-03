---
title: "World Data Preset Contract"
tags: [world, data, seamless]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# World Data Preset Contract

This page defines the world-owned data-plane contract: data presets plus the tag/queue routing rules that surround them. Seamless implementation details remain in [Seamless Data Provider v2](../architecture/seamless_data_provider_v2.md), while graph and queue resolution remain in [DAG Manager](../architecture/dag-manager.md).

<a id="62-데이터-preset-onramp"></a>
## 1. Data preset on-ramp

The T3 P0-M1 goal is that `world + data preset` is enough for Runner/CLI to wire the correct Seamless instance automatically and inject it into `StreamInput.history_provider`.

### 1.1 Contract

1. The world is the data-plane SSOT and must include `data.presets[]`.
2. `data.presets[].preset` names a Seamless preset ID; storage, backfill, live, schema, and SLA implementations are resolved through the Seamless preset map.
3. Runner/CLI default to the first preset, and `--data-preset <id>` may only reference IDs declared by the world.
4. If the preset target is unavailable, execution fails fast instead of falling back to an arbitrary legacy provider.

### 1.2 Schema example

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

### 1.3 Field semantics

- `id`: world-local dataset key.
- `preset`: Seamless preset key. `family.source.market.interval` is the recommended shape.
- `universe`: default symbol/tag query. Strategy inputs can refine it further.
- `window`: warmup and minimum history requirements; it should align with world `data_currency`.
- `seamless`: SLA, conformance, and backfill overrides.
- `live`: acceptable live lag and partial-pass policy.

### 1.4 Standard preset map

| preset ID | Storage/backfill | Live feed | Default SLA/Conformance | Typical use |
| --- | --- | --- | --- | --- |
| `ohlcv.binance.spot.1m` | QuestDB + CCXT(Binance) backfill | Binance WS `kline@1m` | `baseline` / `strict-blocking` | Crypto 1m momentum |
| `ohlcv.polygon.us_equity.1d` | QuestDB + Polygon REST backfill | none | `tolerant-partial` / `strict-blocking` | US equity EOD |
| `ohlcv.nautilus.crypto.1m` | Nautilus DataCatalog | none | `baseline` / `strict-blocking` | Research/backtests |
| `ohlcv.nautilus.binance.1m` | Nautilus DataCatalog | CCXT Pro WS | `baseline` / `strict-blocking` | Historical + live |
| `ohlcv.nautilus.binance.1h` | Nautilus DataCatalog | CCXT Pro WS | `baseline` / `strict-blocking` | Hourly historical + live |

### 1.5 Nautilus notes

- `nautilus.catalog`: historical-only path.
- `nautilus.full`: Nautilus historical plus CCXT Pro live.
- When `nautilus_trader` is missing, raise `NautilusPresetUnavailableError`.

### 1.6 Contract-test hooks

- Keep world data preset examples in `tests/e2e/core_loop/worlds/core-loop-demo.yml`.
- Expected behavior:
  - missing preset => Runner/CLI fail
  - declared preset => Gateway/WorldService stubs return the preset ID and Runner wires the matching Seamless preset

## 2. Tag/interval to queue-namespace rules

For multi-upstream and multi-asset strategies, TagQueryNode needs DAG Manager, Gateway, and Seamless to share the same tag, interval, and namespace rules.

### 2.1 Tags

- ComputeNode and Queue objects carry tags describing asset class, venue, and data family.
- TagQueryNode and TagQueryManager query Gateway `GET /queues/by_tag` using that tag set plus interval.

### 2.2 Interval

- The `interval` query parameter in `GET /queues/by_tag` is the queue interval in seconds and must match node/queue definitions exactly.
- `interval_ms` in the world preset should stay aligned with the same interval convention.

### 2.3 Namespace

- When topic namespaces are enabled, Gateway may apply `{world_id}.{execution_domain}.<topic>` prefixes.
- Matching tags and intervals are not enough by themselves; world and execution domain boundaries still isolate queue sets.

### 2.4 Relation to Seamless

- Seamless presets decide how queues are filled.
- TagQuery decides which existing queues should be read.
- That means world preset `universe`/`interval_ms`, DAG Manager tag+interval rules, and Gateway `/queues/by_tag` semantics must evolve together.

{{ nav_links() }}
