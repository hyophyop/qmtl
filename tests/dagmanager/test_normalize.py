from qmtl.dagmanager.normalize import (
    normalize_execution_domain,
    normalize_version,
    stringify,
)


def test_stringify_trims_and_handles_none():
    assert stringify(None) == ""
    assert stringify("  value  ") == "value"
    assert stringify(42) == "42"


def test_normalize_version_cleans_and_defaults():
    assert normalize_version(None) == "v1"
    assert normalize_version("  V2  ") == "V2"
    assert normalize_version("release candidate!") == "release-candidate"
    assert normalize_version("--") == "v1"
    assert normalize_version(3) == "3"


def test_normalize_execution_domain_lowercases_and_defaults():
    assert normalize_execution_domain(None) == "live"
    assert normalize_execution_domain("Backtest") == "backtest"
    assert normalize_execution_domain("  PAPER  ") == "paper"
