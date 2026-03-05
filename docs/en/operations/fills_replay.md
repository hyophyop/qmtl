# Fill Replay Runbook

This runbook records why fill replay is currently excluded from Gateway's
public surface.

## Security

The `/fills` endpoint requires a Bearer token signed with the shared HMAC
secret. The token must carry `world_id` and `strategy_id` claims that scope the
request.

## Current Behavior

The current build does not expose `GET /fills/replay`. Replay delivery is not
yet a supported public contract, so the placeholder route was removed instead
of advertising a partial implementation.

## Future Implementation Note

When replay delivery is implemented, this runbook should be updated with the
final request contract, security model, and operational validation steps.
