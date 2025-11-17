from __future__ import annotations

"""Shim to expose check_doc_sync under qmtl/scripts for tests.

Delegates to the project-level script at ``scripts/check_doc_sync.py``.
"""

from pathlib import Path
import importlib.util


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "check_doc_sync.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location("check_doc_sync", _SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Unable to load {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_doc_sync(*args, **kwargs):
    mod = _load()
    return mod.check_doc_sync(*args, **kwargs)
