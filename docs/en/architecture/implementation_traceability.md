---
title: "QMTL Implementation Traceability"
tags:
  - architecture
  - traceability
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# QMTL Implementation Traceability

## Purpose

This document keeps an explicit link between the normative `Concept ID`s and the
current implementation. The design documents prioritize capabilities and semantic
contracts to reduce ambiguity; this document tracks which code and tests currently
back those rules.

## Status Labels

- `normative-only`: a design rule that does not require direct code mapping
- `planned`: present in the normative docs, but not yet implemented
- `partial`: has implementation and/or evidence, but is not yet complete as a first-class concept
- `implemented`: has representative code and test evidence

## Tooling Mapping

The YAML block below is the authoritative traceability payload consumed by
`scripts/check_design_drift.py`.

```yaml
traceability:
  - concept_id: PRIN-CAPABILITY-FIRST
    source_doc: design_principles.md
    status: normative-only
  - concept_id: PRIN-COMPOSITION-OVER-EXCEPTIONS
    source_doc: design_principles.md
    status: normative-only
  - concept_id: PRIN-SEMANTIC-CONSTRAINTS
    source_doc: design_principles.md
    status: normative-only
  - concept_id: PRIN-CORE-NEUTRALITY
    source_doc: design_principles.md
    status: normative-only
  - concept_id: PRIN-EXPLICIT-BOUNDARIES
    source_doc: design_principles.md
    status: normative-only
  - concept_id: PRIN-EXTENSION-ADDS-CONTRACTS
    source_doc: design_principles.md
    status: normative-only
  - concept_id: PRIN-PROFILES-ARE-EXAMPLES
    source_doc: design_principles.md
    status: normative-only

  - concept_id: CAP-OBSERVATION
    source_doc: capability_map.md
    status: implemented
    code:
      - qmtl/runtime/sdk/node.py
      - qmtl/runtime/io/ccxt_live_feed.py
      - qmtl/runtime/io/nautilus_catalog_source.py
    tests:
      - tests/qmtl/runtime/io/test_ccxt_live_feed.py
      - tests/qmtl/runtime/io/test_nautilus_catalog_source.py
  - concept_id: CAP-FEATURE-EXTRACTION
    source_doc: capability_map.md
    status: implemented
    code:
      - qmtl/runtime/transforms/order_book_imbalance.py
      - qmtl/runtime/indicators/microprice_priority.py
    tests:
      - tests/qmtl/runtime/transforms/test_order_book_imbalance.py
      - tests/qmtl/runtime/indicators/test_microprice_priority.py
  - concept_id: CAP-LABELING
    source_doc: capability_map.md
    status: implemented
    code:
      - qmtl/runtime/nodesets/labeling.py
      - qmtl/runtime/labeling/triple_barrier.py
    tests:
      - tests/qmtl/runtime/labeling/test_triple_barrier.py
      - tests/qmtl/runtime/nodesets/test_label_guardrails.py
  - concept_id: CAP-INFERENCE
    source_doc: capability_map.md
    status: partial
    code:
      - qmtl/runtime/transforms/trade_signal.py
      - qmtl/runtime/transforms/llrti_hazard.py
    tests:
      - tests/qmtl/runtime/transforms/test_trade_signal.py
      - tests/qmtl/runtime/transforms/test_llrti.py
  - concept_id: CAP-DECISION
    source_doc: capability_map.md
    status: partial
    code:
      - qmtl/runtime/transforms/position_intent.py
      - qmtl/runtime/pipeline/order_types.py
    tests:
      - tests/qmtl/runtime/transforms/test_position_intent.py
      - tests/qmtl/runtime/sdk/test_intent.py
  - concept_id: CAP-EXECUTION-PLANNING
    source_doc: capability_map.md
    status: partial
    code:
      - qmtl/runtime/nodesets/recipes.py
      - qmtl/runtime/pipeline/execution_nodes/sizing.py
    tests:
      - tests/qmtl/runtime/nodesets/test_recipes.py
      - tests/qmtl/runtime/sdk/test_sizing_weight_integration.py
  - concept_id: CAP-EXECUTION-STATE
    source_doc: capability_map.md
    status: partial
    code:
      - qmtl/runtime/sdk/portfolio.py
      - qmtl/runtime/sdk/execution_modeling/engine.py
    tests:
      - tests/qmtl/runtime/sdk/test_portfolio.py
      - tests/qmtl/runtime/sdk/execution_modeling/test_integration.py
  - concept_id: CAP-EXECUTION-ADAPTERS
    source_doc: capability_map.md
    status: implemented
    code:
      - qmtl/runtime/sdk/brokerage_client.py
      - qmtl/services/gateway/routes/fills.py
    tests:
      - tests/qmtl/runtime/sdk/test_brokerage_client_fake.py
      - tests/qmtl/services/gateway/test_fills_webhook.py
  - concept_id: CAP-RISK-POLICY
    source_doc: capability_map.md
    status: implemented
    code:
      - qmtl/runtime/sdk/risk/controls.py
      - qmtl/runtime/pipeline/execution_nodes/risk.py
    tests:
      - tests/qmtl/runtime/sdk/test_risk_controls.py
      - tests/qmtl/runtime/sdk/risk_management/test_risk_integration.py

  - concept_id: SEM-CAUSAL-STREAM
    source_doc: semantic_types.md
    status: partial
    code:
      - qmtl/runtime/sdk/node.py
      - qmtl/runtime/sdk/cache_view.py
    tests:
      - tests/qmtl/runtime/sdk/test_multi_input_node.py
      - tests/qmtl/runtime/sdk/test_cache_view_helpers.py
  - concept_id: SEM-DELAYED-STREAM
    source_doc: semantic_types.md
    status: implemented
    code:
      - qmtl/runtime/nodesets/labeling.py
      - qmtl/runtime/nodesets/base.py
    tests:
      - tests/qmtl/runtime/nodesets/test_label_guardrails.py
      - tests/qmtl/runtime/labeling/test_meta_labeling.py
  - concept_id: SEM-IMMUTABLE-ARTIFACT
    source_doc: semantic_types.md
    status: implemented
    code:
      - qmtl/runtime/sdk/feature_store/base.py
      - qmtl/runtime/sdk/feature_store/plane.py
    tests:
      - tests/qmtl/runtime/sdk/test_feature_artifact_plane.py
      - tests/qmtl/runtime/sdk/test_cache_view_helpers.py
  - concept_id: SEM-MUTABLE-EXECUTION-STATE
    source_doc: semantic_types.md
    status: partial
    code:
      - qmtl/runtime/sdk/portfolio.py
      - qmtl/runtime/sdk/execution_modeling/models.py
    tests:
      - tests/qmtl/runtime/sdk/test_portfolio.py
      - tests/qmtl/runtime/sdk/execution_modeling/test_helpers.py
  - concept_id: SEM-DECISION-VALUE
    source_doc: semantic_types.md
    status: partial
    code:
      - qmtl/runtime/transforms/position_intent.py
      - qmtl/runtime/pipeline/order_types.py
    tests:
      - tests/qmtl/runtime/transforms/test_position_intent.py
      - tests/qmtl/runtime/sdk/test_intent.py
  - concept_id: SEM-COMMAND-VALUE
    source_doc: semantic_types.md
    status: partial
    code:
      - qmtl/runtime/pipeline/execution_nodes/publishing.py
      - qmtl/runtime/sdk/trade_execution_service.py
    tests:
      - tests/qmtl/runtime/transforms/test_trade_order_publisher.py
      - tests/qmtl/runtime/sdk/test_trade_execution_service.py

  - concept_id: DEC-SCORE
    source_doc: decision_algebra.md
    status: partial
    code:
      - qmtl/runtime/transforms/trade_signal.py
    tests:
      - tests/qmtl/runtime/transforms/test_trade_signal.py
  - concept_id: DEC-DIRECTION
    source_doc: decision_algebra.md
    status: partial
    code:
      - qmtl/runtime/transforms/trade_signal.py
    tests:
      - tests/qmtl/runtime/transforms/test_trade_signal.py
  - concept_id: DEC-POSITION-TARGET
    source_doc: decision_algebra.md
    status: implemented
    code:
      - qmtl/runtime/transforms/position_intent.py
    tests:
      - tests/qmtl/runtime/transforms/test_position_intent.py
  - concept_id: DEC-ORDER-INTENT
    source_doc: decision_algebra.md
    status: implemented
    code:
      - qmtl/runtime/pipeline/order_types.py
      - qmtl/runtime/sdk/pretrade.py
    tests:
      - tests/qmtl/runtime/sdk/test_intent.py
      - tests/qmtl/runtime/sdk/test_order_gate_integration.py
  - concept_id: DEC-QUOTE-INTENT
    source_doc: decision_algebra.md
    status: planned
  - concept_id: PLAN-POSITION-PLANNER
    source_doc: decision_algebra.md
    status: partial
    code:
      - qmtl/runtime/nodesets/recipes.py
      - qmtl/runtime/pipeline/execution_nodes/sizing.py
    tests:
      - tests/qmtl/runtime/nodesets/test_recipes.py
      - tests/qmtl/runtime/sdk/test_sizing_weight_integration.py
  - concept_id: PLAN-QUOTE-PLANNER
    source_doc: decision_algebra.md
    status: planned
  - concept_id: CONTRACT-CORE-LOOP-GOLDEN-PATH
    source_doc: core_loop.md
    status: partial
    code:
      - qmtl/runtime/sdk/runner.py
      - qmtl/runtime/sdk/submit.py
      - qmtl/interfaces/cli/submit.py
    tests:
      - tests/e2e/core_loop/test_runner_submit_contract.py
      - tests/qmtl/interfaces/cli/test_submit_output.py
      - tests/qmtl/runtime/sdk/test_worldservice_eval_contract.py
  - concept_id: CONTRACT-WORLD-LIFECYCLE
    source_doc: world_lifecycle.md
    status: partial
    code:
      - qmtl/services/worldservice/routers/campaigns.py
      - qmtl/services/worldservice/routers/promotions.py
      - qmtl/automation/campaign_executor.py
    tests:
      - tests/qmtl/services/worldservice/test_worldservice_api.py
      - tests/qmtl/automation/test_campaign_executor.py
      - tests/qmtl/interfaces/cli/test_world_cli.py
  - concept_id: CTRL-CAMPAIGN-TICK
    source_doc: core_loop_world_automation.md
    status: implemented
    code:
      - qmtl/services/worldservice/routers/campaigns.py
      - qmtl/automation/campaign_executor.py
      - qmtl/interfaces/cli/world.py
    tests:
      - tests/qmtl/services/worldservice/test_worldservice_api.py
      - tests/qmtl/automation/test_campaign_executor.py
      - tests/qmtl/interfaces/cli/test_world_cli.py
  - concept_id: CTRL-LIVE-PROMOTION-GOVERNANCE
    source_doc: core_loop_world_automation.md
    status: partial
    code:
      - qmtl/services/worldservice/routers/promotions.py
      - qmtl/interfaces/cli/world.py
      - qmtl/services/worldservice/services.py
    tests:
      - tests/qmtl/services/worldservice/test_worldservice_api.py
      - tests/qmtl/interfaces/cli/test_world_cli.py
  - concept_id: CTRL-WORLD-ALLOCATION-TWO-STEP
    source_doc: rebalancing_contract.md
    status: implemented
    code:
      - qmtl/services/worldservice/routers/allocations.py
      - qmtl/services/worldservice/routers/rebalancing.py
      - qmtl/interfaces/cli/world.py
      - qmtl/runtime/sdk/submit.py
    tests:
      - tests/qmtl/services/worldservice/test_worldservice_api.py
      - tests/qmtl/interfaces/cli/test_world_cli.py
      - tests/e2e/test_rebalancing_duplicate_intent.py
  - concept_id: CTRL-REBALANCING-SCHEMA-HANDSHAKE
    source_doc: rebalancing_contract.md
    status: implemented
    code:
      - qmtl/services/worldservice/routers/rebalancing.py
      - qmtl/services/worldservice/api.py
      - qmtl/services/gateway/routes/rebalancing.py
      - qmtl/services/gateway/controlbus_consumer.py
    tests:
      - tests/qmtl/services/worldservice/test_worldservice_api.py
      - tests/qmtl/services/gateway/test_rebalancing_execute_contract.py
      - tests/qmtl/services/gateway/test_controlbus_consumer.py
```

{{ nav_links() }}
