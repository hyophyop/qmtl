---
title: "Shadow Execution Domain E2E"
tags: [guide, shadow, execution_domain, e2e]
author: "QMTL Team"
last_modified: 2025-11-22
---

# Shadow Execution Domain E2E

This guide validates the `execution_domain=shadow` path end-to-end (submission → Gateway → ControlBus/WebSocket → Runner) and shows a minimal local workflow. The contract follows the [Architecture Glossary](../architecture/glossary.md#shadow-execution-domain).

## Quick verification (automated test)

- Install dev deps: `uv pip install -e .[dev]`
- Run in parallel: \
  `uv run -m pytest -W error -n auto tests/e2e/shadow/test_shadow_end_to_end.py`
  - Ensures `ComputeContextService` keeps the World decision (`effective_mode=shadow`)
  - Verifies ControlBus → WS hub `queue_update`/`tagquery.upsert` carry `world_id` and `execution_domain`
  - Confirms Runner uses the same context while hard-blocking order dispatch

## Manual workflow (local, in-process)

1. **Gateway context check**  
   ```python
   from qmtl.services.gateway.submission.context_service import ComputeContextService
   from qmtl.services.gateway.models import StrategySubmit

   submit = StrategySubmit(dag_json="{}", meta={"execution_domain": "shadow"}, world_ids=["shadow-world"], node_ids_crc32=0)
   svc = ComputeContextService(world_client=None)  # retains shadow even without WS
   ctx = await svc.build(submit)
   assert ctx.execution_domain == "shadow"
   ```

2. **ControlBus → WebSocket path**  
   - Check that `queue_update` payloads include `world_id` and `execution_domain`. Example:
     ```json
     {
       "tags": ["shadow-tag"],
       "interval": 60,
       "queues": [{"queue": "q-shadow", "global": false}],
       "match_mode": "any",
       "world_id": "shadow-world",
       "execution_domain": "shadow",
       "version": 1
     }
     ```
   - The same (tags, interval, domain) combination triggers `tagquery.upsert`, keeping shadow namespace isolated.

3. **Runner order gating**  
   ```python
   from qmtl.foundation.common.compute_key import ComputeContext
   from qmtl.runtime.sdk.runner import Runner
   from qmtl.runtime.transforms.publisher import TradeOrderPublisherNode
   from qmtl.runtime.sdk.node import Node

   ctx = ComputeContext(world_id="shadow-world", execution_domain="shadow")
   Runner.set_enable_trade_submission(True)
   service = type("S", (), {"orders": [], "post_order": lambda self, o: self.orders.append(o)})()
   Runner.set_trade_execution_service(service)

   src = Node(name="sig", interval=1, period=1)
   pub = TradeOrderPublisherNode(src)
   src.apply_compute_context(ctx)
   pub.apply_compute_context(ctx)
   Runner.feed_queue_data(pub, src.node_id, 1, 0, {"action": "BUY", "size": 1.0})
   assert service.orders == []  # orders are blocked in shadow domain
   ```

## Notes

- The code snippets mirror the automated test (`{{ code_url('tests/e2e/shadow/test_shadow_end_to_end.py') }}`), so they can be replayed in the same environment after the test passes.
- Shadow remains: live-input mirror, orders OFF, isolated namespace; Gateway/WS policy gates (`X-Allow-Live`, `allow_live`) still apply.
