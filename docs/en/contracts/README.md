---
title: "Product Contracts"
tags:
  - contracts
  - architecture
  - product
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# Product Contracts

## Purpose

This section describes the **minimum surface contracts** that QMTL users and higher-level clients need to understand.

It answers questions such as:

- What is the minimum contract for strategy authors and SDK consumers?
- Which surfaces are read-only, and where do operator approval and audit begin?
- How far does the Core Loop product contract go before operational handoff?

Normative service boundaries and SSOT definitions live in [Architecture](../architecture/README.md).
Operational procedures and approval flows live in [Operations](../operations/README.md).

## Document map

- [Core Loop Contract](core_loop.md): the single submission path and result contract for strategy authors.
- [World Lifecycle Contract](world_lifecycle.md): backtest → paper → live transitions and operator handoff boundaries.

## Audience

- strategy authors
- SDK/CLI consumers
- reviewers evaluating the product-facing surface

## Non-goals

- internal implementation classes or service-to-service protocol detail
- deployment, approval, and rollback runbooks
- detailed implementation-status tracking

{{ nav_links() }}
