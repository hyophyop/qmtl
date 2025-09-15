from __future__ import annotations

import importlib
import hashlib

import pytest

from qmtl.common import hash_bytes as exported_hash_bytes
from qmtl.common.hashutils import hash_bytes

try:  # pragma: no cover - optional dependency in tests
    from blake3 import blake3 as _blake3
except Exception:  # pragma: no cover - runtime fallback
    _blake3 = None


@pytest.mark.skipif(_blake3 is None, reason="blake3 module is not available")
def test_hash_bytes_prefers_blake3() -> None:
    data = b"hash-me"
    assert hash_bytes(data) == f"blake3:{_blake3(data).hexdigest()}"
    # Ensure the helper is also re-exported at package level for convenience.
    assert exported_hash_bytes(data) == f"blake3:{_blake3(data).hexdigest()}"


def test_hash_bytes_falls_back_to_sha256(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("qmtl.common.hashutils")
    monkeypatch.setattr(module, "_blake3", None)
    digest = module.hash_bytes(b"fallback")
    assert digest == f"sha256:{hashlib.sha256(b'fallback').hexdigest()}"


def test_hash_bytes_falls_back_on_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("qmtl.common.hashutils")

    class BrokenHash:
        def __call__(self, data: bytes):  # type: ignore[override]
            raise RuntimeError("boom")

    monkeypatch.setattr(module, "_blake3", BrokenHash())
    digest = module.hash_bytes(b"boom")
    assert digest == f"sha256:{hashlib.sha256(b'boom').hexdigest()}"
