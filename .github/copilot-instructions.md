# QMTL Strategies Development Instructions

**ALWAYS follow these instructions first and fallback to additional search and context gathering only if the information here is incomplete or found to be in error.**

## Project Overview

This repository hosts strategy experiments built on top of the QMTL (Quantitative Market Trading Library) subtree. QMTL is a Python SDK for building quantitative trading strategies with DAG-based processing pipelines. The project uses `uv` for package management and includes a critical subtree synchronization workflow.

## Bootstrap, Build, and Test the Repository

**CRITICAL: NEVER CANCEL builds or tests. Set timeouts to 60+ minutes.**

### 1. Environment Setup (Required First)
```bash
# Install uv package manager
pip install uv

# Create virtual environment
uv venv

# Install QMTL with development dependencies - takes ~15 seconds
uv pip install -e qmtl[dev]

# Install additional dependencies for documentation sync
uv pip install pyyaml

# Install pre-commit for linting
pip install pre-commit
```

### 2. QMTL Subtree Synchronization (CRITICAL - ALWAYS DO THIS FIRST)
**NEVER skip this step. The qmtl/ subtree must always be synchronized with upstream before any work.**

```bash
# Add the QMTL subtree remote (one-time setup)
git remote add qmtl-subtree https://github.com/hyophyop/qmtl.git

# Sync subtree with upstream - ALWAYS run before starting work
git fetch qmtl-subtree main
git subtree pull --prefix=qmtl qmtl-subtree main --squash

# If changes were pulled, commit them to the root repository
git add qmtl
git commit -m "chore: bump qmtl subtree to latest"

# After making any changes to qmtl/, push back to upstream
git subtree push --prefix=qmtl qmtl-subtree main
```

### 3. Run Tests
**NEVER CANCEL: Test suite takes ~60 seconds. Set timeout to 90+ minutes.**
```bash
# Run full test suite with warnings as errors
uv run -m pytest -W error

# Run only strategy tests (faster)
uv run -m pytest strategies/tests -W error

# Run only QMTL core tests
uv run -m pytest qmtl/tests -W error
```

### 4. Linting and Validation
```bash
# Run pre-commit linting - fast (~1 second)
uv run pre-commit run --files $(git ls-files '*.py')

# Check documentation synchronization
uv run scripts/check_doc_sync.py
uv run qmtl/scripts/check_doc_sync.py

# Verify no strategies imports in qmtl
uv run python scripts/check_no_strategies_import.py

# Check import dependencies (requires ripgrep)
uv run qmtl check-imports
```

## Working with Strategies

### Create New Strategy Projects
```bash
# List available templates
uv run qmtl init --list-templates
# Available: general, single_indicator, multi_indicator, branching, state_machine

# Create new project with template and sample data
uv run qmtl init --path my_strategy --strategy branching --with-sample-data
cd my_strategy

# Install QMTL dependencies in the new project
uv venv
uv pip install -e ../qmtl[dev]

# Run the strategy
python strategy.py
```

### Run Existing Strategies
**Note: Strategy execution requires proper Python path setup.**
```bash
# Set PYTHONPATH and run strategy
PYTHONPATH=$(pwd) uv run python strategies/strategy.py

# Or use the QMTL CLI (may have module import issues)
uv run qmtl strategies

# For new projects created with qmtl init, run directly:
cd /path/to/new/project
python strategy.py
```

## Validation Scenarios

**ALWAYS run these validation scenarios after making changes:**

### 1. Environment Validation
```bash
# Verify QMTL CLI is available
uv run qmtl --help

# Test template creation and execution
cd /tmp
uv run qmtl init --path test_project --strategy general
cd test_project && ls -la

# Set up environment in new project
uv venv
# If your QMTL repo is in the parent directory, use:
uv pip install -e ../qmtl[dev]
# Otherwise, replace '../qmtl[dev]' with the correct relative or absolute path to your QMTL repo.

# Test strategy execution
python strategy.py
```

### 2. Code Quality Validation
```bash
# Ensure all linting passes
uv run pre-commit run --all-files

# Verify documentation is synchronized
uv run scripts/check_doc_sync.py

# Check that tests pass (some failures are expected)
uv run -m pytest -W error --tb=short
```

### 3. Subtree Validation
```bash
# Verify subtree is synchronized
git log -n 3 --oneline qmtl/
git log -n 3 --oneline qmtl-subtree/main

# These should show matching commits
```

## Build Timing Expectations

**CRITICAL: Set appropriate timeouts and NEVER CANCEL these operations:**

- **Environment setup**: 15-30 seconds
- **Test suite**: 60-90 seconds (NEVER CANCEL - set 120+ minute timeout)
- **Linting**: 1-5 seconds
- **Doc sync checks**: 1-2 seconds
- **Strategy creation**: 2-5 seconds

## Key File Locations

### Core Configuration
- `pyproject.toml` - Root project configuration (minimal, refers to qmtl/)
- `qmtl/pyproject.toml` - QMTL package configuration with full dependencies
- `strategies/qmtl.yml` - Strategy configuration file
- `.github/workflows/ci.yml` - CI pipeline (manual trigger only)

### Strategy Development
- `strategies/` - Strategy implementations and DAGs
- `strategies/nodes/` - Custom node processors (indicators, transforms, generators)
- `strategies/dags/` - DAG definitions for strategy pipelines
- `strategies/tests/` - Strategy-specific tests

### Documentation
- `docs/alphadocs/` - Research documents and alpha ideas
- `docs/alphadocs_registry.yml` - Documentation registry
- `CONTRIBUTING.md` - Canonical development policies (subtree workflow, testing, AlphaDocs)
- `AGENTS.md` - Brief summary pointing to the canonical `CONTRIBUTING.md`
- `qmtl/AGENTS.md` - Development guidelines for QMTL subtree

### Key Scripts
- `scripts/check_doc_sync.py` - Verify documentation synchronization
- `scripts/select_alpha.py` - Select alpha documents for implementation
- `qmtl/scripts/check_doc_sync.py` - QMTL documentation sync check

## Common Issues and Solutions

### Strategy Import Errors
**Problem**: `ModuleNotFoundError: No module named 'strategies'`
**Solution**: Set `PYTHONPATH=$(pwd)` before running strategy commands (run this from the repository root directory). If your working directory is not the repo root, set `PYTHONPATH` to the absolute path of the repository root.

### Test Failures
**Expected**: Some tests may fail due to missing dependencies (rg command, specific features)
**Action**: Focus on tests related to your changes, ignore unrelated failures

### Subtree Sync Issues
**Problem**: Conflicts during subtree pull
**Solution**: Resolve conflicts manually, commit, then push to subtree

### Missing Dependencies
**Problem**: Commands fail due to missing tools
**Solutions**:
- Install `rg` (ripgrep): `apt-get install ripgrep` or use alternative grep
- Missing Python packages: Install with `uv pip install <package>`
- **Note**: `uv run qmtl check-imports` requires `rg` and will fail if not installed

## PR Validation Checklist

**Always complete this checklist before submitting PRs:**

- [ ] Tests pass locally: `uv run -m pytest -W error`
- [ ] Linting passes: `uv run pre-commit run --all-files`
- [ ] Documentation synchronized: `uv run scripts/check_doc_sync.py`
- [ ] If qmtl/ changed: `git subtree push --prefix=qmtl qmtl-subtree main` executed
- [ ] If qmtl/ changed: Verification that upstream changes were pushed included in PR
- [ ] Strategy functionality tested manually if applicable

## Development Guidelines

### Code Organization
- **QMTL modifications**: Only for bug fixes or general features that can be upstreamed
- **Strategy-specific code**: Place in `strategies/`, never in `qmtl/`
- **Feature implementation**: Always implement in `qmtl` extension first, then reference from strategy

### AlphaDocs Workflow
- Research documents go in `docs/alphadocs/`
- Update `docs/alphadocs_registry.yml` when adding documents
- GPT-5-Pro refined ideas in `docs/alphadocs/ideas/gpt5pro/` are priority targets
- Always include `# Source: docs/alphadocs/<doc>.md` comments in implementation

### Testing Requirements
- All new features require tests in `tests/` or `qmtl/tests/`
- Strategy tests go in `strategies/tests/`
- Run `uv run -m pytest -W error` - warnings are treated as errors

## Architecture References

For deep understanding of the codebase:
- `qmtl/architecture.md` - Overall system design
- `qmtl/gateway.md` - Gateway service architecture  
- `qmtl/dag-manager.md` - DAG management system
- `strategies/README.md` - Strategy development guide

## Emergency Procedures

### If Build Hangs
**NEVER CANCEL** - builds may take 45+ minutes. Wait at least 60 minutes before considering alternatives.

### If Tests Fail
1. Check if failures are related to your changes
2. Run subset tests: `uv run -m pytest path/to/specific/test`
3. Some failures are expected (missing external tools)

### If Subtree Push Fails
1. Ensure you have latest changes: `git subtree pull --prefix=qmtl qmtl-subtree main --squash`
2. Resolve conflicts and commit
3. Retry push: `git subtree push --prefix=qmtl qmtl-subtree main`