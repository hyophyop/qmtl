# WorldService Gating Walkthrough

This guide explains how the example project interacts with the latest
WorldService gating flow.

## Key concepts

- **Two-phase apply** – Every promotion freezes activation (`freeze=true`,
  `active=false`), switches the execution domain, and finally unfreezes once
  the new activation snapshot is acknowledged by Gateway/SDK consumers.
- **Gating policy document** – Promotion requests must supply a policy defining
  dataset fingerprints, snapshot isolation, and per-domain edge overrides.
- **Activation envelopes** – Gateway relays `freeze`/`drain` flags together with
  weights so strategies can block or scale orders immediately.

## Example assets

- [`worldservice/gating_policy.example.yml`](../worldservice/gating_policy.example.yml)
  captures the minimal policy accepted by `parse_gating_policy`. It
  demonstrates how to disable cross-domain edges before promotion and enable
  them afterwards.
- [`scripts/worldservice_apply_demo.py`](../scripts/worldservice_apply_demo.py)
  posts an apply payload containing dummy metrics, a generated `run_id`, and the
  parsed gating policy body.

## Running the demo

1. Start Gateway and WorldService. For a local run without Docker:
   - WorldService (SQLite + Redis):
     ```bash
     export QMTL_WORLDSERVICE_DB_DSN=sqlite:///worlds.db
     export QMTL_WORLDSERVICE_REDIS_DSN=redis://localhost:6379/0
     uv run uvicorn qmtl.services.worldservice.api:create_app --factory --host 0.0.0.0 --port 8080
     ```
   - Gateway (optionally proxying WorldService):
     - In `qmtl/examples/qmtl.yml` set `gateway.worldservice_url: http://localhost:8080`
       and `gateway.enable_worldservice_proxy: true`.
    - Start: `qmtl service gateway --config qmtl/examples/qmtl.yml`
   - Alternatively, use the provided Docker Compose stack.
2. Inspect the payload without side effects:
   ```bash
   python -m qmtl.examples.scripts.worldservice_apply_demo --world-id demo --dry-run
   ```
3. Drop `--dry-run` to send the request. The script prints the JSON response so
   you can confirm `phase="completed"` and see which strategies remain active.

The payload produced by the script is ready for manual tweaks—adjust strategy
metrics or swap in a different gating policy to test promotion guardrails.
