Title: Finalize Order/Fill/Portfolio Schemas and Register in Schema Registry
Labels: api, schemas, reference

Summary
Promote the informal shapes in `docs/reference/api/order_events.md` to versioned JSON Schemas and register them in the Schema Registry.

Tasks
- Define JSON Schemas: `OrderPayload`, `OrderAck`, `ExecutionFillEvent`, `PortfolioSnapshot`.
- Add to `docs/reference/schemas.md` and the registry storage/location used by Gateway/SDK.
- Provide Python pydantic models or dataclasses for convenience.
- Add conformance tests for producers/consumers (SDK and Gateway webhook).

Acceptance Criteria
- Schemas versioned and published; CI validates examples.
- Producers/consumers accept unknown fields and validate required ones.

