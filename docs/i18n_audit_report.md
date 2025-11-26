# i18n Audit Report

This report lists markdown files that appear to mix languages or be mis-localized.
Heuristics flag Korean pages with too little Hangul text, and English pages with Hangul present.

- ko_low_hangul: 2.6% hangul, 76.4% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/reference/_inventory.md`
- ko_low_hangul: 11.5% hangul, 67.5% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/lean_brokerage_model.md`
- ko_low_hangul: 12.4% hangul, 62.7% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/guides/migration_bc_removal.md`
- ko_low_hangul: 12.5% hangul, 67.9% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/reference/CHANGELOG.md`
- ko_low_hangul: 12.8% hangul, 42.7% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/operations/exchange_calendars.md`
- ko_low_hangul: 12.9% hangul, 73.6% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/archive/ccxt-seamless-legacy-audit.md`
- ko_low_hangul: 12.9% hangul, 59.8% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/templates/index.md`
- ko_low_hangul: 14.3% hangul, 76.2% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/reference/schemas/index.md`
- ko_low_hangul: 16.7% hangul, 59.9% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/io/ccxt-questdb.md`
- ko_low_hangul: 17.1% hangul, 66.3% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/gateway.md`
- ko_low_hangul: 17.1% hangul, 46.4% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/archive/README.md`
- ko_low_hangul: 17.3% hangul, 59.2% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/execution_state.md`
- ko_low_hangul: 17.6% hangul, 63.7% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/execution_nodes.md`
- ko_low_hangul: 17.6% hangul, 60.7% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/layered_template_system.md`
- ko_low_hangul: 18.3% hangul, 50.5% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/reference/api/order_events.md`
- ko_low_hangul: 18.3% hangul, 63.6% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/worldservice.md`
- ko_low_hangul: 18.4% hangul, 61.5% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/operations/timing_controls.md`
- ko_low_hangul: 19.2% hangul, 62.6% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/operations/backfill.md`
- ko_low_hangul: 19.6% hangul, 62.9% latin — `/Users/munseungjin/workspace/research/qmtl/docs/ko/reference/api/brokerage.md`

---

## /Users/munseungjin/workspace/research/qmtl/docs/ko/reference/_inventory.md
- Kind: ko_low_hangul — Hangul: 2.6%, Latin: 76.4%

Sample lines:
{% raw %}
- L21: - `docs/MAINTENANCE_SCHEDULE.md`
- L28: - `.github/copilot-instructions.md`
- L34: - `docs/architecture/README.md`
- L35: - `docs/architecture/architecture.md`
- L36: - `docs/architecture/ccxt-seamless-integrated.md`
- L37: - `docs/architecture/controlbus.md`
- L38: - `docs/architecture/dag-manager.md`
- L39: - `docs/architecture/exchange_node_sets.md`
- L40: - `docs/architecture/execution_nodes.md`
- L41: - `docs/architecture/execution_state.md`
- L42: - `docs/architecture/gateway.md`
- L43: - `docs/architecture/glossary.md`
- L44: - `docs/architecture/layered_template_system.md`
- L45: - `docs/architecture/lean_brokerage_model.md`
- L46: - `docs/architecture/seamless_data_provider_v2.md`
- L47: - `docs/architecture/worldservice.md`
- L53: - `docs/archive/ccxt-seamless-legacy-audit.md`
- L58: - `docs/design/seamless_data_provider.md`
- L59: - `docs/design/yaml_config_overhaul.md`
- L65: - `docs/guides/build_nodeset_sdk.md`
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/lean_brokerage_model.md
- Kind: ko_low_hangul — Hangul: 11.5%, Latin: 67.5%

Sample lines:
{% raw %}
- L13: - Architecture Overview (README.md)
- L14: - QMTL Architecture (architecture.md)
- L17: - WorldService (worldservice.md)
- L39: * 계좌 유형, **RequiredFreeBuyingPowerPercent**(유휴 매수력 비율), 브로커별 **CanSubmit/CanExecuteOrder** 등 주문 가능 판정 API. ([QuantConnect (https://www.lean.io/docs/v2/lean-engine/class-reference/I...
- L40: * **Order Properties / Time-in-Force**:
- L42: * GTC/GTD/IOC/FOK 등의 만기 규칙, 브로커 기본 값 설정. ([QuantConnect (https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-properties?utm_source=chatgpt.com)][4], [Q...
- L43: * **심볼 속성(SymbolProperties / DB)**:
- L45: * **최소 호가단위(tick size)**, **로트/최소 주문수량**, **계약승수**, 종목 통화 등. 주문 호가/수량 검증·라운딩에 사용. ([QuantConnect (https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Secur...
- L49: * **SecurityExchangeHours / MarketHoursDatabase**:
- L51: * 정규·프리·애프터 마켓 시간, 조기폐장/휴장 포함. 오더 실행 가능 시간 판정에 사용. ([QuantConnect (https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SecurityExchangeHours....
- L55: * **Buying Power Model (IBuyingPowerModel)**:
- L57: * 주문 접수 전 **증거금/레버리지 가능 여부**와 최대 수량 판정. 브로커/시간대/상품에 따라 복잡한 규칙을 캡슐화. ([QuantConnect (https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/buying-power?utm_source...
- L63: * 주문타입별(시장가/지정가/스탑/개장·폐장가 등) **체결가·체결수량** 결정. **개장/폐장 옥션가격** 사용 가능. ([QuantConnect (https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concept...
- L72: * 브로커·시장별 **거래 수수료** 구조(고정·퍼센트·브로커 특화). 체결 이벤트에 비용 반영. ([QuantConnect (https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/key-concepts?utm_so...
- L73: * **Settlement Model (ISettlementModel)**:
- L75: * 현금 결제 주기/규칙, 시간 경과에 따른 자금 적용(Scan/ApplyFunds 호출). ([QuantConnect (https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/key-concepts?utm_source=chat...
- L78: * 차입금에 대한 일할 이자/월말 정산 등 마진 이자 모델. ([QuantConnect (https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/margin-interest-rate/key-concepts?utm_source=chatgpt.com)...
- L81: * 다통화 포트폴리오 현금 장부·환율변환·총자산 반영. ([QuantConnect (https://www.quantconnect.com/docs/v2/writing-algorithms/portfolio/cashbook?utm_source=chatgpt.com)][16], [QuantConnect (https://www.l...
- L87: * 대차 가능한 주식 수량·대차비용 모델링 → 없으면 공매도 주문 거부. ([QuantConnect (https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IShortableProvider.html?utm_...
- L91: * **IBrokerage / Factory / Data 핸들러**:
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/guides/migration_bc_removal.md
- Kind: ko_low_hangul — Hangul: 12.4%, Latin: 62.7%

Sample lines:
{% raw %}
- L28: from qmtl.runtime.sdk import Runner
- L31: Runner.submit(strategy, world="demo")
- L41: qmtl submit strategy.py --mode backtest --world demo
- L47: qmtl submit strategy.py --mode paper --world demo
- L48: qmtl submit strategy.py --mode live  # live execution
- L76: from qmtl.runtime.brokerage.simple import PerShareFeeModel, VolumeShareSlippageModel
- L82: from qmtl.runtime.brokerage import PerShareFeeModel, VolumeShareSlippageModel
- L87: - [x] `Runner.backtest` / `Runner.dryrun` / `Runner.live` / `Runner.run` / `Runner.offline` 호출을 `Runner.submit(..., mode=...)`로 교체
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/reference/CHANGELOG.md
- Kind: ko_low_hangul — Hangul: 12.5%, Latin: 67.9%

Sample lines:
{% raw %}
- L8: <!-- Generated from ../CHANGELOG.md; do not edit manually -->
- L16: - `NodeCache.snapshot()` has been deprecated in favor of the read-only `CacheView` returned by `NodeCache.view()`. Strategy code should avoid calling the snapshot helper.
- L17: - Added `coverage()` and `fill_missing()` interfaces for history providers and removed `start`/`end` arguments from `StreamInput`.
- L18: - `TagQueryNode.resolve()` has been removed. Use `TagQueryManager.resolve_tags()` to fetch queue mappings before execution.
- L19: - Added `Node.add_tag()` to attach tags after node creation.
- L25: PR 제목: ci: temporarily disable GitHub Actions auto triggers; update docs for manual verification (2025-08-14)
- L30: - `.github/workflows/ci.yml`, `qmtl/.github/workflows/ci.yml`에서 push/pull_request 트리거 제거, workflow_dispatch만 남김 (CI 임시 비활성화)
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/operations/exchange_calendars.md
- Kind: ko_low_hangul — Hangul: 12.8%, Latin: 42.7%

Sample lines:
{% raw %}
- L16: | NYSE/NASDAQ | 04:00 | 09:30–16:00 | — | 16:00–20:00 | US/Eastern |
- L23: from qmtl.runtime.sdk.timing_controls import MarketHours
- L32: early_closes={date(2024, 12, 24): time(13, 0)},
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/archive/ccxt-seamless-legacy-audit.md
- Kind: ko_low_hangul — Hangul: 12.9%, Latin: 73.6%

Sample lines:
{% raw %}
- L13: 감사는 각 문서를 통합 청사진인 `ccxt-seamless-integrated.md` (../architecture/ccxt-seamless-integrated.md)와 비교하고,
- L21: ### `ccxt-seamless-gpt5high.md`
- L25: | **Data Model** (`ts, open, high, low, close, volume` schema + interval semantics) | ✅ Migrated | Documented under “Data Model & Interval Semantics” in `ccxt-seamless-integrated.m...
- L26: | **Control Planes → Rate Limiting** (Redis/process split description) | ✅ Migrated | Expanded rate-limiter reference table and environment variable guidance now live in the integr...
- L27: | **Configuration & Recipes** (Python example using `EnhancedQuestDBProvider`) | ✅ Migrated | Example provider wiring added to the Data Plane section of the integrated blueprint. |
- L28: | **Operational Guidance** (env vars, metrics, monitoring references) | ✅ Migrated | Operational Practices now enumerate coordinator and Redis env vars plus enriched metrics. |
- L29: | **Testing** (mark `slow`, prefer recorded responses) | ✅ Migrated | Implementation and Testing Guidance sections call out pytest preflight, recorded fixtures, and `slow` marks. |
- L30: | **Extensions** (future ccxt.pro live feed, synthetic series, trades→bars repair) | ✅ Migrated | Captured in the new “Extensions” section appended to the integrated document. |
- L32: ### `ccxt-seamless-gpt5codex.md`
- L36: | **Feature Artifact Plane guardrails** (dataset_fingerprint-as_of discipline preventing domain bleed) | ✅ Migrated | Integrated doc now details read-only sharing, provenance, and ...
- L37: | **CCXT worker metadata workflow** (computing dataset_fingerprint/as_of at snapshot time) | ✅ Migrated | Publication workflow pseudo-code specifies when workers conform, fingerpri...
- L38: | **Artifact storage policy** (versioned retention in Feature Artifact store) | ✅ Migrated | Storage policy section clarifies hot vs cold roles, versioning, and watermark promotion...
- L39: | **Observability metrics** (`backfill_completion_ratio` alongside SLA counters) | ✅ Migrated | Operational Practices → Metrics Catalog lists SLA timers, backfill ratios, and gatin...
- L40: | **Implementation roadmap** (connector packaging, Seamless adapter layer, persistence, domain gating, observability) | ✅ Migrated | Migration Path and Validation Benchmarks outlin...
- L46: | **Comprehensive configuration schema** (retry tuning, metrics catalog, partitioning, fingerprint options) | ✅ Migrated | Configuration blueprint now includes retry knobs, observa...
- L47: | **Reference implementation snippets** (`conform_frame`, `compute_fingerprint`, `maybe_publish_artifact`, domain gating helper) | ✅ Migrated | Publication workflow pseudo-code rep...
- L48: | **Operations & observability checklist** (metric names, alert thresholds, env vars) | ✅ Migrated | Operational Practices enumerate metrics, alerts, and environment variables, con...
- L49: | **Storage strategy (Hot vs. Cold) and stabilization workflow** | ✅ Migrated | Dedicated storage strategy section documents QuestDB vs artifact responsibilities and promotion sequ...
- L50: | **Migration pathway & acceptance criteria** | ✅ Migrated | Migration Path and Validation Benchmarks capture the seven-step rollout and readiness checks. |
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/templates/index.md
- Kind: ko_low_hangul — Hangul: 12.9%, Latin: 59.8%

Sample lines:
{% raw %}
- L11: - {{ code_link('qmtl/examples/templates/backend_stack.example.yml', text='백엔드 스택 구성 템플릿') }}
- L12: - {{ code_link('qmtl/examples/templates/local_stack.example.yml', text='로컬 스택 구성 템플릿') }}
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/reference/schemas/index.md
- Kind: ko_low_hangul — Hangul: 14.3%, Latin: 76.2%


## /Users/munseungjin/workspace/research/qmtl/docs/ko/io/ccxt-questdb.md
- Kind: ko_low_hangul — Hangul: 16.7%, Latin: 59.9%

Sample lines:
{% raw %}
- L14: - `CcxtOHLCVFetcher` + `CcxtBackfillConfig`
- L15: - `CcxtQuestDBProvider` (QuestDB + AutoBackfill 전략 래퍼)
- L16: - 내부적으로 `AugmentedHistoryProvider` + `FetcherBackfillStrategy` 사용
- L21: - `uv pip install -e .[dev,ccxt,questdb]`
- L23: - Docker 예시: `docker run -p 8812:8812 -p 9000:9000 questdb/questdb:latest`
- L27: - Docker 예시: `docker run -p 6379:6379 redis:7-alpine`
- L28: - 설정: `connectors.ccxt_rate_limiter_redis: redis://localhost:6379/0`
- L29: - (레거시) 환경변수: `QMTL_CCXT_RATE_LIMITER_REDIS=redis://localhost:6379/0`
- L34: from qmtl.runtime.sdk import StreamInput
- L35: from qmtl.runtime.io import CcxtQuestDBProvider
- L37: provider = CcxtQuestDBProvider.from_config({
- L41: "questdb": {"dsn": "postgresql://localhost:8812/qdb", "table": "crypto_ohlcv"},
- L46: "scope": "cluster",  # 또는 "process"
- L47: "redis_dsn": "redis://localhost:6379/0",
- L53: price = StreamInput(interval="60s", period=120, history_provider=provider)
- L56: # from qmtl.runtime.sdk import Runner
- L57: # await Runner._ensure_history(strategy, start, end)
- L64: participant Node as Node/StreamInput
- L65: participant HP as AugmentedHistoryProvider
- L67: participant BF as FetcherBackfillStrategy
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/gateway.md
- Kind: ko_low_hangul — Hangul: 17.1%, Latin: 66.3%

Sample lines:
{% raw %}
- L13: *Research‑Driven Draft v1.2 — 2025‑06‑10*
- L16: - Architecture Overview (README.md)
- L17: - QMTL Architecture (architecture.md)
- L19: - WorldService (worldservice.md)
- L21: - Lean Brokerage Model (lean_brokerage_model.md)
- L24: - 운영 가이드: 리스크 관리 (../operations/risk_management.md), 타이밍 컨트롤 (../operations/timing_controls.md)
- L25: - 레퍼런스: Brokerage API (../reference/api/brokerage.md), Commit‑Log 설계 (../reference/commit_log.md), World/Activation API (../reference/api_world.md)
- L38: |  G‑01  | Diff submission queuing **loss‑free** under 1 k req/s burst  | `lost_requests_total = 0` |
- L39: |  G‑02  | **≤ 150 ms** p95 end‑to‑end latency (SDK POST → Warm‑up ack) | `gateway_e2e_latency_p95` |
- L71: SDK --> Ingest --> FIFO --> Worker --> DAGM
- L72: DAGM --> Worker --> FSM --> WS --> SDK
- L81: ## S2 · API Contract (**OpenAPI 3.1 excerpt**)
- L87: summary: Submit local DAG for execution
- L91: schema: { $ref: '#/components/schemas/StrategySubmit' }
- L93: '202': { $ref: '#/components/responses/Ack202' }
- L101: '200': { $ref: '#/components/responses/Status200' }
- L104: summary: Fetch queues matching tags and interval
- L114: schema: { type: string, enum: [any, all] }
- L133: Clients SHOULD specify ``match_mode`` to control tag matching behavior. When
- L134: omitted, Gateway defaults to ``any`` for backward compatibility.
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/archive/README.md
- Kind: ko_low_hangul — Hangul: 17.1%, Latin: 46.4%


## /Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/execution_state.md
- Kind: ko_low_hangul — Hangul: 17.3%, Latin: 59.2%

Sample lines:
{% raw %}
- L20: NEW --> PARTIALLY_FILLED: fill(q < qty)
- L23: NEW --> EXPIRED: tif=IOC/FOK unmet
- L24: PARTIALLY_FILLED --> PARTIALLY_FILLED: fill(q < remaining)
- L25: PARTIALLY_FILLED --> FILLED: fill(q == remaining)
- L26: PARTIALLY_FILLED --> CANCELED: cancel()
- L27: PARTIALLY_FILLED --> EXPIRED: tif window end
- L34: | NEW | fill(q < qty) | PARTIALLY_FILLED |
- L38: | PARTIALLY_FILLED | fill(q < remaining) | PARTIALLY_FILLED |
- L39: | PARTIALLY_FILLED | fill(q == remaining) | FILLED |
- L40: | PARTIALLY_FILLED | cancel() | CANCELED |
- L41: | PARTIALLY_FILLED | tif window end | EXPIRED |
- L49: 참고: Brokerage API (../reference/api/brokerage.md), Lean Brokerage Model (lean_brokerage_model.md)
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/execution_nodes.md
- Kind: ko_low_hangul — Hangul: 17.6%, Latin: 63.7%

Sample lines:
{% raw %}
- L3: tags: [architecture, execution, nodes]
- L21: price[price stream] --> alpha[alpha]
- L24: hist --> combine[combine (fan-in)]
- L25: combine --> signal[trade_signal]
- L26: signal --> orders[publish_orders]
- L34: from qmtl.runtime.sdk import Node, StreamInput
- L35: from qmtl.runtime.transforms import alpha_history_node, TradeSignalGeneratorNode
- L36: from qmtl.runtime.pipeline.execution_nodes import RouterNode
- L37: from qmtl.runtime.pipeline.micro_batch import MicroBatchNode
- L39: price = StreamInput(interval="60s", period=2)
- L42: data = view[price][price.interval]
- L45: prev, last = data[-2][1]["close"], data[-1][1]["close"]
- L48: alpha = Node(input=price, compute_fn=compute_alpha, name="alpha")
- L49: history = alpha_history_node(alpha, window=30)
- L51: def alpha_with_trend_gate(view):
- L52: hist_data = view[history][history.interval]
- L53: price_data = view[price][price.interval]
- L54: if not hist_data or not price_data:
- L56: hist_series = hist_data[-1][1]  # list[float]
- L57: closes = [row[1]["close"] for row in price_data]
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/layered_template_system.md
- Kind: ko_low_hangul — Hangul: 17.6%, Latin: 60.7%

Sample lines:
{% raw %}
- L17: - Architecture Overview (README.md)
- L18: - Strategy Development Workflow (../guides/strategy_workflow.md)
- L19: - SDK Tutorial (../guides/sdk_tutorial.md)
- L43: subgraph "Strategy Pipeline Layers"
- L44: D[Data Layer<br/>StreamInput, DataProvider]
- L45: S[Signal Layer<br/>Indicators, Transforms, Alpha]
- L46: E[Execution Layer<br/>PreTrade, Sizing, Execution]
- L47: B[Brokerage Layer<br/>CCXT, IBKR Integration]
- L48: M[Monitoring Layer<br/>Metrics, Logging]
- L67: | **Data** | 데이터 공급 및 수집 | StreamInput, HistoryProvider, DataProvider |
- L68: | **Signal** | 알파 생성 및 신호 변환 | Indicators, Transforms, Alpha Logic |
- L69: | **Execution** | 주문 실행 및 관리 | PreTradeGate, Sizing, ExecutionNode |
- L70: | **Brokerage** | 거래소 통합 | CCXT, IBKR, Custom Brokers |
- L71: | **Monitoring** | 관측 및 메트릭 수집 | Metrics, Event Recorder, Logging |
- L107: qmtl project init --path my_backtest --preset minimal
- L110: qmtl project init --path my_prod --preset production
- L113: qmtl project init --path my_research --preset research
- L120: qmtl project init --path my_strategy --layers data,signal
- L123: qmtl project init --path my_strategy --layers data,signal,execution
- L126: qmtl project init --path my_strategy --layers data,signal,execution,brokerage,monitoring
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/reference/api/order_events.md
- Kind: ko_low_hangul — Hangul: 18.3%, Latin: 50.5%

Sample lines:
{% raw %}
- L17: - 키: `world_id|strategy_id|symbol|client_order_id` (또는 결정적 해시)
- L21: - 키: `world_id|strategy_id|symbol|order_id`
- L25: - 키: `world_id|[strategy_id]|snapshot`
- L39: "correlation_id": "ord-20230907-0001",
- L51: "metadata": {"source": "node_set/binance_spot"}
- L63: "raw": {"provider_payload": "..."}
- L72: "correlation_id": "ord-20230907-0001",
- L96: "BTC/USDT": {"qty": 0.01, "avg_cost": 25010.0, "mark": 24995.0}
- L98: "metrics": {"exposure": 0.25, "leverage": 1.1}
- L116: "source": "broker/binanceusdm",
- L119: "datacontenttype": "application/json",
- L120: "data": { /* ExecutionFillEvent */ }
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/architecture/worldservice.md
- Kind: ko_low_hangul — Hangul: 18.3%, Latin: 63.6%

Sample lines:
{% raw %}
- L3: tags: [architecture, world, policy]
- L18: - 일급 개념으로서의 ExecutionDomain: 월드별 `backtest | dryrun | live | shadow`
- L19: - 2‑단계 Apply: Freeze/Drain → Switch → Unfreeze, `run_id`로 멱등성 보장
- L33: - world_id (pk, slug), name, description, owner, labels[]
- L34: - created_at, updated_at, state (ACTIVE|SUSPENDED|DELETED)
- L35: - default_policy_version, allow_live (bool), circuit_breaker (bool)
- L38: - (world_id, version) (pk), yaml (text), checksum, status (DRAFT|ACTIVE|DEPRECATED)
- L39: - created_by, created_at, valid_from (optional)
- L42: - Key: world:<id>:active → { strategy_id|side : { active, weight, etag, run_id, ts } }
- L46: - id, world_id, actor, event (create/update/apply/evaluate/activate/override)
- L47: - request, result, created_at, correlation_id
- L58: - WorldNodeRef (DB): `(world_id, node_id, execution_domain)` → `status` (`unknown|validating|valid|invalid|running|paused|stopped|archived`), `last_eval_key`, `annotations{}`
- L59: - Validation (DB): `eval_key = blake3:(NodeID||WorldID||ContractID||DatasetFingerprint||CodeVersion||ResourcePolicy)` (**'blake3:' 접두사 필수**), `result`, `metrics{}`, `timestamp`
- L61: - **EdgeOverride (DB, WVG scope):** 월드-로컬 도달성 제어 레코드. `(world_id, src_node_id, dst_node_id, active=false, reason)` 형태로 특정 월드에서 비활성화할 에지를 명시한다. 구현은 `EdgeOverrideRepository` ({{ code...
- L70: - POST /worlds | GET /worlds | GET /worlds/{id} | PUT /worlds/{id} | DELETE /worlds/{id}
- L73: - POST /worlds/{id}/policies  (upload new version)
- L74: - GET /worlds/{id}/policies   (list) | GET /worlds/{id}/policies/{v}
- L75: - POST /worlds/{id}/set-default?v=V
- L78: - POST /worlds/{id}/bindings        (upsert WSB: bind `strategy_id` to world)
- L79: - GET  /worlds/{id}/bindings        (list; filter by `strategy_id`)
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/operations/timing_controls.md
- Kind: ko_low_hangul — Hangul: 18.4%, Latin: 61.5%

Sample lines:
{% raw %}
- L19: from qmtl.runtime.sdk.timing_controls import MarketHours, MarketSession
- L20: from datetime import date, datetime, time, timezone
- L29: early_closes={date(2024, 12, 24): time(13, 0)},
- L33: ts = datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc)
- L35: assert session is MarketSession.REGULAR
- L46: - `validate_timing(timestamp)`: `(is_valid, reason, session)` 반환
- L51: from qmtl.runtime.sdk.timing_controls import TimingController
- L53: controller = TimingController(allow_pre_post_market=False)
- L54: valid, reason, session = controller.validate_timing(ts)
- L56: print(f"Blocked {session}: {reason}")
- L64: from qmtl.runtime.sdk.timing_controls import validate_backtest_timing
- L66: issues = validate_backtest_timing(strategy)
- L67: for node, node_issues in issues.items():
- L69: print(issue["reason"], issue["datetime"])
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/operations/backfill.md
- Kind: ko_low_hangul — Hangul: 19.2%, Latin: 62.6%

Sample lines:
{% raw %}
- L41: from qmtl.runtime.sdk import QuestDBHistoryProvider
- L43: source = QuestDBHistoryProvider(
- L44: dsn="postgresql://user:pass@localhost:8812/qdb",
- L47: # with an external fetcher supplying missing rows
- L49: # source = QuestDBHistoryProvider(
- L50: #     dsn="postgresql://user:pass@localhost:8812/qdb",
- L63: from qmtl.runtime.sdk import DataFetcher
- L66: async def fetch(self, start: int, end: int, *, node_id: str, interval: str) -> pd.DataFrame:
- L68: "https://api.binance.com/api/v3/klines"
- L69: f"?symbol={node_id}&interval={interval}"
- L70: f"&startTime={start * 1000}&endTime={end * 1000}"
- L72: async with httpx.AsyncClient() as client:
- L73: data = (await client.get(url)).json()
- L76: {"ts": int(r[0] / 1000), "open": float(r[1]), "close": float(r[4])}
- L82: loader = QuestDBHistoryProvider(
- L83: dsn="postgresql://user:pass@localhost:8812/qdb",
- L112: from qmtl.runtime.sdk import AugmentedHistoryProvider, FetcherBackfillStrategy
- L113: from qmtl.runtime.io import QuestDBBackend
- L115: backend = QuestDBBackend(dsn="postgresql://user:pass@localhost:8812/qdb")
- L116: provider = AugmentedHistoryProvider(
{% endraw %}

## /Users/munseungjin/workspace/research/qmtl/docs/ko/reference/api/brokerage.md
- Kind: ko_low_hangul — Hangul: 19.6%, Latin: 62.9%

Sample lines:
{% raw %}
- L18: - 인터페이스: BuyingPowerModel, FillModel, SlippageModel, FeeModel
- L19: - Fill 모델: MarketFillModel, LimitFillModel, StopMarketFillModel, StopLimitFillModel (IOC/FOK는 TIF로 지원)
- L20: - 슬리피지 모델: NullSlippageModel, ConstantSlippageModel, SpreadBasedSlippageModel, VolumeShareSlippageModel
- L21: - 수수료 모델: PerShareFeeModel, PercentFeeModel, MakerTakerFeeModel, TieredExchangeFeeModel, BorrowFeeModel, CompositeFeeModel, IBKRFeeModel(거래소/규제 수수료와 유동성 리베이트가 포함된 티어 기반 per-share)
- L23: ExchangeHoursProvider(정규/프리/포스트), ShortableProvider(`StaticShortableProvider` + `ShortableLot` 로 일일 공매도 수량 제공)
- L24: - 프로파일: BrokerageProfile, SecurityInitializer, ibkr_equities_like_profile()
- L30: A[Activation Gate] --> B[Symbol/Tick/Lot Validation]
- L50: from qmtl.runtime.brokerage import (
- L65: MakerTakerFeeModel(maker_rate=0.0002, taker_rate=0.0007),
- L68: symbols=SymbolPropertiesProvider(),  # 내장된 JSON/CSV 심볼 DB 로드
- L69: hours=ExchangeHoursProvider(allow_pre_post_market=False, require_regular_hours=True),
- L70: shortable=StaticShortableProvider({"AAPL": ShortableLot(quantity=1000, fee=0.01)}),
- L74: from qmtl.runtime.brokerage import IBKRFeeModel
- L75: fee = IBKRFeeModel(minimum=1.0, exchange_fee_remove=0.0008, exchange_fee_add=-0.0002, regulatory_fee_remove=0.0001)
- L93: - 주문 유형: market, limit, stop, stop-limit, market-on-open, market-on-close, trailing-stop. Limit/StopLimit은 주문 객체의 `limit_price`, `stop_price` 를 사용하고, trailing-stop은 `trail_amount` ...
- L98: from qmtl.runtime.brokerage import ibkr_equities_like_profile
- L100: profile = ibkr_equities_like_profile()
- L109: from qmtl.runtime.brokerage.ccxt_profile import make_ccxt_brokerage
- L113: "binance",               # CCXT ID ("binanceusdm" 은 선물용)
- L120: model_default = make_ccxt_brokerage(
{% endraw %}
