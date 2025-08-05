# Contributing Guide

This project demonstrates how to build and test QMTL strategy packages.

## Setting up the QMTL CLI

1. Initialize the QMTL submodule:
   ```bash
   git submodule update --init --recursive
   ```
2. Install the CLI in editable mode to expose the `qmtl` command:
   ```bash
   pip install -e qmtl
   ```
3. Verify the command works:
   ```bash
   qmtl --help
   ```

## Adding a new strategy

1. Copy `strategies/example_strategy` to a new folder, e.g. `strategies/my_strategy`.
2. Implement your strategy class inside `__init__.py`.
3. Update `strategy.py` to import and run your strategy:
   ```python
   from my_strategy import MyStrategy

   if __name__ == "__main__":
       MyStrategy().run()
   ```
4. Run the strategy to ensure it executes correctly:
   ```bash
   cd strategies
   python strategy.py
   ```
