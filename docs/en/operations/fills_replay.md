# Fill Replay Runbook

This runbook captures the current status of fill replay in Gateway.

## Security

The `/fills` endpoint requires a Bearer token signed with the shared HMAC
secret. The token must carry `world_id` and `strategy_id` claims that scope the
request.

## Current Behavior

The current build exposes only a placeholder `GET /fills/replay` endpoint. It
returns `202 Accepted` with `"replay not implemented in this build"` and does
not republish historical fills.

## Future Implementation Note

When replay delivery is implemented, this runbook should be updated with the
final request contract and operational validation steps.
