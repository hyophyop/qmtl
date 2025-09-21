# DAG Manager Compute Context Rollout

The September 2025 release introduces compute context propagation through
`DiffRequest` and salts `queue_map` keys with a domain-scoped compute key. This
section documents the required compatibility steps and the recommended rolling
deploy sequence.

## Summary

- `DiffService.DiffRequest` now accepts optional fields:
  `world_id`, `execution_domain`, `as_of`, `partition`, and
  `dataset_fingerprint`.
- `DiffService` derives a domain-scoped compute key and appends it to each
  `queue_map` partition key as `...#ck=<hash>`. Downstream consumers must strip
  the `#ck=` suffix (if present) before extracting the `node_id` portion.
- Regenerate all gRPC stubs after bumping the proto minor version (e.g.,
  `dagmanager.proto` v1.4 → v1.5). The Python wheel published for this change
  SHOULD reflect a minor version bump as well (Gateway + DAG Manager packages).

## Rolling Deploy Plan

1. **Prepare Artifacts**
   - Regenerate gRPC stubs (`uv run python -m grpc_tools.protoc ...`).
   - Publish a Gateway build that:
     - forwards the new compute context fields when present,
     - gracefully parses `queue_map` keys containing `#ck=`.
   - Publish a DAG Manager build that understands the new fields and derives the
     compute key.

2. **Upgrade Gateways First**
   - Roll out the new Gateway release across all regions. The updated client is
     backward compatible with the older DAG Manager (queue_map keys without the
     `#ck=` suffix continue to parse correctly).
   - Verify Gateway health endpoints plus the metrics `dagclient_breaker_state`
     and `dagclient_breaker_failures` remain nominal.

3. **Upgrade DAG Manager**
   - Drain one DAG Manager instance at a time and roll forward to the new
     version. Start with a canary, observe:
     - `dagmanager_diff_failures_total`
     - `dagmanager_queue_create_error_total`
     - Gateway ingest success metrics
   - Once stable, proceed with the rest of the pool.

4. **Post-Deploy Validation**
   - Confirm queue map responses now include `#ck=` suffixes and that Gateway
     workers continue to process strategies.
   - Spot check TagQuery lookups and WebSocket queue map broadcasts for the new
     format.

## Rollback Considerations

- If issues arise after upgrading DAG Manager, roll back the service while
  keeping the Gateway release in place. The Gateway tolerates the older
  queue_map format.
- If the Gateway rollback is required, revert the Gateway first and then assess
  whether DAG Manager needs to drop back to the previous build.

Keeping the deployment order (Gateway → DAG Manager) ensures clients never see
`#ck=`-salted keys without the parsing logic needed to handle them.
