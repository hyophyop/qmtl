# GitHub Issues for QMTL Architecture Test Improvements

This directory contains prepared GitHub issue templates for improving QMTL's test coverage of unique architectural features.

## Issues Overview

### Core Loop draft/spec work

- Use `.github/issues/core-loop-contract-draft.md` when opening Core Loop 설계/계약/스펙 작업 이슈.  
  - 목적/범위/배제, 단일 출처 스펙 링크(ko/en), 오픈 질문/결정자, 착수·종료 게이트, 마이그레이션/롤백, 후속 작업 체크리스트가 포함됩니다.  
  - 스펙 본문은 반드시 문서(예: `docs/ko/design/core_loop_roadmap.md`)에만 두고, 이슈에는 링크와 상태(`draft — subject to change`)만 적으세요.  
  - 계약 테스트 스켈레톤은 `@pytest.mark.contract + xfail`로 추가 후, 스펙 확정 시 `xfail`을 제거해 강제 실패로 전환합니다.
  - CI에 Core Loop 계약 스위트(`tests/e2e/core_loop`)가 추가되었습니다. inproc 스택 기준으로 병렬 실행되며, ExecutionDomain default-safe 다운그레이드와 SubmitResult 필드가 커버됩니다.

### High Priority

1. **test-canonical-nodeid-determinism.md**
   - **Focus**: Canonical NodeID generation, BLAKE3 hashing, determinism
   - **Gap**: Parameter canonicalization, dependency sorting, schema compatibility
   - **Impact**: Core to global node reuse strategy

2. **test-gsg-wvg-ssot-boundaries.md**
   - **Focus**: GSG/WVG separation, SSOT boundaries, immutability
   - **Gap**: Cross-service consistency, Gateway non-ownership, EvalKey reproducibility
   - **Impact**: Fundamental to system integrity

3. **test-execution-domain-isolation.md**
   - **Focus**: ComputeKey isolation, domain separation, queue namespacing
   - **Gap**: Cross-domain cache prevention, promotion safety, Feature Artifact Plane
   - **Impact**: Critical for backtest→live safety

4. **test-commit-log-replay-consistency.md**
   - **Focus**: Append-only log, replay determinism, idempotency
   - **Gap**: Recovery scenarios, partition key ordering, exactly-once semantics
   - **Impact**: System recoverability and auditability

### Medium Priority

5. **test-4d-tensor-cache-period-window.md**
   - **Focus**: 4D tensor model, multi-interval windows, eviction
   - **Gap**: Multi-upstream coordination, gap detection, Arrow backend
   - **Impact**: Data processing correctness

6. **test-version-sentinel-canary-rollout.md**
   - **Focus**: Version sentinels, canary deployment, traffic splitting
   - **Gap**: Rollback testing, A/B routing, queue compatibility
   - **Impact**: Safe production deployments

## How to Use

### Option 1: Create Issues via GitHub Web UI

1. Go to https://github.com/hyophyop/qmtl/issues/new
2. Copy content from each `.md` file
3. Set title and labels as specified in front matter
4. Submit issue

### Option 2: Use GitHub CLI (if installed)

```bash
# Install gh CLI if not available
brew install gh  # macOS
# or
apt install gh  # Linux

# Authenticate
gh auth login

# Create issues from files
for file in .github/issues/test-*.md; do
  gh issue create \
    --title "$(grep '^title:' $file | cut -d'"' -f2)" \
    --body-file <(sed '1,/^---$/d; /^---$/,$d' $file) \
    --label "$(grep '^labels:' $file | cut -d' ' -f2-)"
done
```

### Option 3: Bulk Import via GitHub API

See `scripts/import_issues.py` for automated bulk import.

## Test Implementation Priority

Recommended implementation order:

1. **test-canonical-nodeid-determinism** - Foundation for everything else
2. **test-execution-domain-isolation** - Safety-critical for production
3. **test-gsg-wvg-ssot-boundaries** - System integrity
4. **test-commit-log-replay-consistency** - Recoverability
5. **test-4d-tensor-cache-period-window** - Data correctness
6. **test-version-sentinel-canary-rollout** - Deployment safety

## Contributing

When implementing these tests:

1. Follow test structure in existing `tests/` directories
2. Use `pytest` fixtures from `conftest.py`
3. Add tests to CI preflight checks (see `AGENTS.md`)
4. Update documentation when test reveals architectural clarifications
5. Link PRs back to these issues with `Closes #<number>`

## Questions?

- See `docs/architecture/` for detailed specifications
- Check existing tests in `tests/qmtl/` for patterns
- Refer to `AGENTS.md` for development guidelines
