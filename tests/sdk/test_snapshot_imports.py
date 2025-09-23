import importlib
import sys
import builtins
import logging

import pytest


def _remove_modules(prefix: str):
    removed = {}
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            removed[name] = sys.modules.pop(name)
    return removed


def _restore_modules(mods):
    sys.modules.update(mods)


def test_pyarrow_missing(monkeypatch):
    removed = _remove_modules("pyarrow")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("pyarrow"):
            raise ImportError("mocked missing pyarrow")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    sys.modules.pop("qmtl.runtime.sdk.snapshot", None)
    snap = importlib.import_module("qmtl.runtime.sdk.snapshot")
    assert snap.pa is None
    assert snap.pq is None
    sys.modules.pop("qmtl.runtime.sdk.snapshot", None)
    _restore_modules(removed)


def test_fsspec_missing(monkeypatch):
    removed = _remove_modules("fsspec")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fsspec":
            raise ImportError("mocked missing fsspec")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    sys.modules.pop("qmtl.runtime.sdk.snapshot", None)
    snap = importlib.import_module("qmtl.runtime.sdk.snapshot")
    assert snap.fsspec is None
    sys.modules.pop("qmtl.runtime.sdk.snapshot", None)
    _restore_modules(removed)


def test_pyarrow_other_exception_logged(monkeypatch, caplog):
    removed = _remove_modules("pyarrow")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("pyarrow"):
            raise RuntimeError("boom")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    sys.modules.pop("qmtl.runtime.sdk.snapshot", None)
    with caplog.at_level(logging.ERROR):
        snap = importlib.import_module("qmtl.runtime.sdk.snapshot")
    assert snap.pa is None
    assert snap.pq is None
    assert any("pyarrow" in rec.message for rec in caplog.records)
    sys.modules.pop("qmtl.runtime.sdk.snapshot", None)
    _restore_modules(removed)
