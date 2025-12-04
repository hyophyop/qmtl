# Core Loop Roadmap Tasks

Representative issue numbers are in parentheses. Phase 2 is the current focus.

## Phase 0 – Foundations (spec/skeleton)
- Create the Core Loop contract test skeleton first: tests/e2e/core_loop scaffold (#1788).
- Tackle spec work up front:
  - Set direction for SubmitResult/WS schema alignment (#1764, #1771).
  - Define world data preset spec (#1776).
  - Document NodeID/TagQuery determinism rules (#1782).
  - Gather Determinism checklist items/scope (#1785).

## Phase 1 – ExecutionDomain/default-safe vertical slice (drive one mode/domain rule end-to-end)
- Lock WS boundary: WS ExecutionDomain validation/downgrade (#1773).
- Strengthen Runner/CLI input validation (#1767) → implement SDK/CLI default-safe downgrade (#1768).
- Remove Runner submission hints (WS effective_mode first) (#1774).
- Align ComputeContext: apply compute_context rules (#1779) → enforce WS-first rule (#1780).
- Add ExecutionDomain default-safe contract/E2E tests (#1775) + fold into Core Loop contract suite (#1789).
- Current status: Phase 1 is complete.

## Phase 2 – SubmitResult/WS SSOT tidy-up (T1/T2 P0)
- [x] Align SubmitResult ↔ WS envelopes and publish a shared module (#1764, #1771) — CLOSED; lock shared WS/SDK schema location/naming to avoid downstream flips.
- [x] Expose WS results as the SSOT in Runner/CLI/API (#1770) — SubmitResult merges WS first with `precheck` separated; CLI prints WS vs pre-check sections.
- [x] Clean up SDK/CLI SubmitResult output (#1765) — downgrade/default-safe signals exposed; WS vs precheck split with tests (ties into #1789).
- [x] Refresh SDK/strategy guides and ops/dev guides to state “WS is the final truth” (#1766, #1772) — ko/en guidance updated with WS SSOT vs pre-check separation and runbook note.

## Phase 3 – World-based data preset on-ramp (T3 P0)
- [x] Implement Runner/CLI seamless auto-configuration based on the preset spec (#1777) — map `world.data.presets[]` to packaged `data_presets` with Seamless auto-wiring, add `--data-preset`, and seed demo providers by default.
- [x] Add preset-driven examples/guides and wire live examples into CI/contract tests (#1778, #1789) — core-loop demo world carries the standard data preset and the contract test asserts auto-wiring.

## Phase 4 – NodeID/TagQuery + Determinism wrap-up (T4/T5 P0)
- Implement/verify NodeID/TagQuery determinism per engine (#1783) → observe/test (#1784).
- Code the Determinism checklist (#1785) → metrics/dashboards (#1786) → runbook hardening (#1787).
- Expand Core Loop contract suite with NodeID/TagQuery and Determinism cases (#1789).

## Phase 5 – CI gate landing (T6 P0)
- Integrate the Core Loop contract suite as a CI merge blocker (#1790).
- Document how breaking each test maps back to roadmap/architecture intent.

### Parallelization notes
- Phase 1 (ExecutionDomain line) and Phase 2 (SubmitResult/WS SSOT) can proceed partly in parallel,
- Phase 3 (data preset) and Phase 4 (NodeID/Determinism) should wait until Phase 1/2 rules are settled.
