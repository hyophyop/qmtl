---
title: "섀도우 실행 도메인 E2E"
tags: [guide, shadow, execution_domain, e2e]
author: "QMTL Team"
last_modified: 2025-11-22
---

# 섀도우 실행 도메인 E2E

`execution_domain=shadow` 경로가 제출 → Gateway → ControlBus/WS → Runner까지 유지되고 주문 발행이 차단되는지 빠르게 검증하고, 로컬에서 같은 흐름을 재현하는 워크플로우를 정리했습니다. 섀도우 계약은 [아키텍처 용어집](../architecture/glossary.md#shadow-execution-domain)을 따릅니다.

## 빠른 검증(자동 테스트)

- 개발 의존성 설치: `uv pip install -e .[dev]`
- 병렬 실행: \
  `uv run -m pytest -W error -n auto tests/e2e/shadow/test_shadow_end_to_end.py`
  - Gateway `ComputeContextService`가 WS 결정(`effective_mode=shadow`)을 받아 섀도우로 유지하는지
  - ControlBus → WS 허브 `queue_update`/`tagquery.upsert`에 `world_id`·`execution_domain`이 포함되는지
  - Runner가 동일 컨텍스트로 실행하되 주문 발행을 하드 차단하는지 검증합니다.

## 수동 워크플로우(로컬, 인프로세스)

1. **Gateway 컨텍스트 확인**  
   ```python
   from qmtl.services.gateway.submission.context_service import ComputeContextService
   from qmtl.services.gateway.models import StrategySubmit

   submit = StrategySubmit(dag_json="{}", meta={"execution_domain": "shadow"}, world_id="shadow-world", node_ids_crc32=0)
   svc = ComputeContextService(world_client=None)  # WS가 없어도 shadow를 유지
   ctx = await svc.build(submit)
   assert ctx.execution_domain == "shadow"
   ```

2. **ControlBus → WebSocket 경로**  
   - `queue_update` 이벤트 페이로드에 `world_id`와 `execution_domain`이 함께 전달되는지 확인합니다. 예시:
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
   - 동일 (tags, interval, domain) 조합으로 `tagquery.upsert`도 발행되어 섀도우 네임스페이스가 분리됩니다.

3. **Runner 주문 게이팅**  
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
   assert service.orders == []  # shadow 도메인에서는 주문 발행 차단
   ```

## 참고

- 코드 예제는 자동 테스트(`{{ code_url('tests/e2e/shadow/test_shadow_end_to_end.py') }}`)와 동일한 흐름을 따르므로, 테스트 통과 후 동일 환경에서 반복 가능합니다.
- 섀도우는 라이브 입력 미러 + 주문 OFF + 네임스페이스 격리가 핵심 계약입니다. Gateway/WS 정책 게이트(`X-Allow-Live`, `allow_live`)는 그대로 적용됩니다.
