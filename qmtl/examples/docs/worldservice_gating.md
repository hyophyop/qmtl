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

1. Start Gateway and WorldService (for example via `uv run qmtl dev` or the
   provided Docker compose).
2. Inspect the payload without side effects:
   ```bash
   python -m qmtl.examples.scripts.worldservice_apply_demo --world-id demo --dry-run
   ```
3. Drop `--dry-run` to send the request. The script prints the JSON response so
   you can confirm `phase="completed"` and see which strategies remain active.

The payload produced by the script is ready for manual tweaks—adjust strategy
metrics or swap in a different gating policy to test promotion guardrails.
