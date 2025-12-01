---
title: "SDK Auto Returns Design Comparison Memo"
tags: [design, returns, validation, sr]
author: "QMTL Team"
last_modified: 2025-11-29
status: draft
---

# SDK Auto Returns Design Comparison Memo

## 0. As-Is / To-Be Summary

- As-Is
  - This memo compares multiple auto_returns design drafts. None of the options are fully implemented in the runtime today; the system still assumes manual returns provisioning.
- To-Be
  - The unified design in `auto_returns_unified_design.md` is the forward-looking baseline. This comparison stays as historical/decision context with the As-Is banner kept in place so readers can separate design from implementation status.

> **Compared docs**
> - SDK-wide design: [`auto_derive_returns_proposal.md`](../../ko/design/auto_derive_returns_proposal.md)
> - SR-focused sketch: [`sr_auto_returns_integration_sketch.md`](./sr_auto_returns_integration_sketch.md)

Canonical content lives in `docs/ko/...`; this English page mirrors the Korean draft so English builds succeed while translations are completed.

This memo briefly contrasts two drafts for **auto-deriving returns** in the QMTL SDK.

## 1. Shared Premises

Both documents assume:

- Keep defaults intact; auto-derive is **opt-in** only.
- If a strategy supplies `returns`/`equity`/`pnl`, those values **always win first**.
- ValidationPipeline/WorldService should continue expecting “already computed returns.”
- The main goal is to **reduce boilerplate** for price-based simple strategies (feeds/demos/smoke).

## 2. `auto_derive_returns_proposal.md` (SDK-wide) Pros/Cons

### Pros

- **End-to-end completeness**
  - Provides an SDK-wide API/implementation sketch (Runner.submit, ValidationPipeline, a new `returns_derive.py` module) plus observability ideas like `_extract_returns_from_strategy` extensions and `SubmitResult.returns_source` metadata.
- **Concrete API proposals**
  - Suggests `auto_derive_returns: bool | str | None`, `returns_field`, and `derive_returns_from_price_node(...)` signatures that are easy to port.
  - Mirrors options on ValidationPipeline for flows that do not go through Runner.
- **Test/checklist ready**
  - Includes an implementation checklist that clarifies scope and impact.

### Cons / Open Items

- **Limited expressiveness**
  - The `auto_derive_returns: bool | str` pattern is simple but grows awkward as node/field/method/constraints expand; the API could get cluttered fast.
- **Option spread into ValidationPipeline**
  - Adding new parameters to ValidationPipeline widens the contract surface and risks pushing auto-derive behavior into the validation layer instead of keeping it in the Runner pre-processing tier.
- **SR/Seamless context is separate**
  - The design targets general SDK users and does not explicitly address SR integration (Seamless Provider, ExpressionDagBuilder, etc.).

## 3. `sr_auto_returns_integration_sketch.md` (SR × Runner.submit) Pros/Cons

### Pros

- **SR/Seamless-focused context**
  - Tied to `sr_integration_proposal.md`, assuming **standard price nodes/fields with Seamless Data Provider/Expression DAG**, which clarifies how SR templates would inject settings when calling Runner.submit.
- **More flexible config model**
  - Uses `auto_returns: bool | AutoReturnsConfig | None` with `AutoReturnsConfig(node, field, method, min_length, ...)` for a **structured, extensible** option set (log returns, multiple node shapes, etc.).
- **Layer separation emphasized**
  - Keeps auto-returns in Runner.submit pre-processing and leaves ValidationPipeline/WorldService contracts untouched, keeping the blast radius smaller.

### Cons / Open Items

- **Looser implementation detail**
  - Provides only conceptual pieces (`AutoReturnsConfig`, `derive_returns_from_price(...)`); still needs the SDK-wide details from `auto_derive_returns_proposal.md` when implementing.
- **Less coverage of general SDK flows**
  - Focused on SR/Seamless contexts, with less guidance for manual/backtest users.

## 4. Combined View and Blend Ideas

Summary:

- `auto_derive_returns_proposal.md`
  - Pros: **Concrete, implementation-ready** design with checklists across the SDK.
  - Cons: API extensibility is limited; pushes options into ValidationPipeline.
- `sr_auto_returns_integration_sketch.md`
  - Pros: **SR/Seamless-optimized**, flexible config, clear layer boundaries.
  - Cons: Less detailed implementation guidance and general SDK coverage.

A natural blend for implementation:

- Use the **API/module structure** and checklist from `auto_derive_returns_proposal.md`.
- Adopt the **`AutoReturnsConfig` and Runner pre-processing focus** from `sr_auto_returns_integration_sketch.md` for SR integration and extensibility.

This memo remains as context; once a final approach is chosen, fold the relevant content into the primary design docs.

## 5. Feedback Loop Perspective

Here we compare how each design supports a “user feedback loop” where users submit strategies, review metrics, iterate, and resubmit.

### 5.1 What a healthy loop needs

- **Low-friction on-ramp**: easy to submit and see some metrics.
- **Metric fidelity**: even auto-derived returns should correlate with strategy behavior enough to guide interpretation.
- **Gradual upgrade path**: users should be able to start with auto-returns and move to explicit `returns`/`equity`/`pnl` later.
- **Observability**: users must be able to tell whether metrics are derived vs. explicit to avoid misinterpreting signals.

### 5.2 `auto_derive_returns_proposal.md` view

**Strengths**

- Supports fast “see some metrics” flows for many strategy types.
- Metadata like `SubmitResult.returns_source` makes it clear whether results were derived or explicit, reducing the risk of over-trusting derived metrics.
- ValidationPipeline options allow **smoke/demo presets** that allow auto-returns and **production presets** that require explicit returns, aligning with an incremental adoption journey.

**Weak points / cautions**

- If options permeate ValidationPipeline, teams may blur the line between smoke metrics and production metrics.
- The `bool | str` API favors simplicity over expressiveness, which might limit metric fidelity for more structured strategies.

Overall, this approach excels at **broad on-ramp and observability**, but can be coarse for structured SR-like strategies.

### 5.3 `sr_auto_returns_integration_sketch.md` view

**Strengths**

- SR/Seamless focus means **standard price nodes** defined by ExpressionDagBuilder/Seamless Provider, yielding comparable metrics across SR candidates.
- A common config basis keeps SR generations comparable, easing feedback-driven ranking.
- Structured `AutoReturnsConfig` supports staged fidelity upgrades (start with pct_change; later use richer derivations).

**Weak points / cautions**

- Because it is SR-centric, manual strategy users may need extra guidance to interpret differences between SR auto-returns and explicit returns paths.
- If SR templates enable auto-returns by default, users might optimize against derived metrics without realizing it, hurting fidelity if gaps widen from real PnL.

Net: great for **comparable, repeatable measurement within SR cohorts**, but requires careful user education to avoid over-trusting derived metrics.

### 5.4 Blended feedback-loop suggestion

- **On-ramp & observability**
  - Keep metadata like `returns_source` (per `auto_derive_returns_proposal.md`) visible in Runner/World UI, logs, and reports so users always see whether metrics are derived or explicit.
  - Allow auto-returns in smoke/demo presets but **require explicit returns in production presets** to reinforce the “practice → production” path.
- **SR cohort comparability**
  - Apply `AutoReturnsConfig` from `sr_auto_returns_integration_sketch.md` to SR templates so candidate strategies share a common derivation rule.
- **Staged upgrade path**
  - For SR/feed strategies: (1) start with auto-returns for quick filtering, (2) add explicit `returns`/`equity`/`pnl` once candidates meet a bar, (3) enforce explicit returns in production World/presets.

In short:

- Use `auto_derive_returns_proposal.md` for the **broad on-ramp plus observability** aspects.
- Use `sr_auto_returns_integration_sketch.md` for **comparable metrics and configurability** within SR/Expression-based cohorts.
- Together they support a **practical, metric-driven improvement loop**.
