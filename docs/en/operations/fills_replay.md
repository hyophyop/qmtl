# Fill Replay Runbook

This runbook outlines how operators can trigger re-delivery of historical fill
events through the Gateway.

## Security

The `/fills` and `/fills/replay` endpoints require a Bearer token signed with
the shared HMAC secret. The token must carry `world_id` and `strategy_id`
claims that scope the request.

## Replay Procedure

1. Generate a JWT with the appropriate scope.
2. Issue a `POST /fills/replay` request containing `from_ts` and `to_ts` Unix
   timestamps and optional `world_id`/`strategy_id` filters.
3. Monitor the `trade.fills` topic to verify re-delivery. Consumers should
   handle events idempotently.

