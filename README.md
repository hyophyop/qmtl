# qmtl-strategies

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/hyophyop/qmtl)

## Environment Setup

Project dependencies are provided by the QMTL subtree, so local packages are minimized. Prepare your development environment with the following commands:

```bash
uv venv
uv pip install -e ./qmtl[dev]
```

## QMTL Subtree Synchronization

The project includes a `qmtl` subtree. Always fetch the latest changes before starting work.

QMTL is a subtree pulled from a separate repository. Modifications should be minimized and synchronized only after being reflected in the upstream repository. Strategy-level optimizations and experiments should be performed in the root directory, not inside `qmtl/`.

```bash
git fetch qmtl-subtree main
git subtree pull --prefix=qmtl qmtl-subtree main --squash
```
If needed, refer to the setup procedure in [CONTRIBUTING.md](CONTRIBUTING.md) to add the `qmtl-subtree` remote.

## How to Run `qmtl init`

Prerequisite: install the CLI from the subtree in editable mode:

```bash
uv pip install -e ./qmtl[dev]
```

Use the `qmtl init` command to create new strategy projects.

```bash
# List available templates
qmtl init --list-templates

# Create project with branching template and sample data
qmtl init --path my_qmtl_project --strategy branching --with-sample-data
cd my_qmtl_project
```

The generated directory includes `strategy.py`, `qmtl.yml`, `.gitignore`, and packages defining nodes and DAGs: `strategies/nodes/` and `strategies/dags/`. The previous `generators/`, `indicators/`, `transforms/` packages have been relocated under `strategies/nodes/`.

## Strategy Template Creation Procedure

1. Create a new strategy package referencing `strategies/example_strategy`.
2. Implement a `Strategy` subclass in the package's `__init__.py`.

```python
from qmtl.sdk import Strategy

class MyStrategy(Strategy):
    def setup(self):
        pass
```

3. Modify `strategies/strategy.py` to import and run your desired strategy.

```python
from strategies.my_strategy import MyStrategy

if __name__ == "__main__":
    MyStrategy().run()
```

4. If needed, modify `qmtl.yml` for environment configuration, add custom nodes in `strategies/nodes/`, and configure DAGs in `strategies/dags/`. Documentation for previous `generators/`, `indicators/`, `transforms/` has been moved under `strategies/nodes/`.
5. Verify that the strategy works correctly.

```bash
python strategies/strategy.py
```

Alternatively, you can run it through the QMTL CLI subcommand:

```bash
qmtl strategies
```

## Node and DAG Configuration

Node processors are configured in `strategies/nodes/`, and strategy DAGs in `strategies/dags/`. Refer to [strategies/README.md](strategies/README.md) for detailed instructions.

## Additional Learning Resources

For an overview of the project architecture, refer to the [qmtl/architecture.md]`qmtl/docs/architecture/architecture.md` document.

