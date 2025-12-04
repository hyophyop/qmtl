import pytest

from qmtl.services.worldservice.storage.constants import (
    DEFAULT_EXECUTION_DOMAIN,
    DEFAULT_WORLD_NODE_STATUS,
)
from qmtl.services.worldservice.storage.normalization import (
    _normalize_execution_domain,
    _normalize_world_node_status,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, DEFAULT_EXECUTION_DOMAIN),
        ("", DEFAULT_EXECUTION_DOMAIN),
        ("   ", DEFAULT_EXECUTION_DOMAIN),
        ("default", DEFAULT_EXECUTION_DOMAIN),
        ("compute-only", "backtest"),
        ("compute_only", "backtest"),
        ("paper", "dryrun"),
        ("sim", "dryrun"),
        ("  LIVE  ", "live"),
        ("DryRun", "dryrun"),
        (" shadow ", "shadow"),
    ],
)
def test_normalize_execution_domain_defaults_and_lowercases(raw: object, expected: str) -> None:
    assert _normalize_execution_domain(raw) == expected


@pytest.mark.parametrize("raw", ["weird", 123])
def test_normalize_execution_domain_rejects_unknown_values(raw: object) -> None:
    with pytest.raises(ValueError, match="unknown execution_domain"):
        _normalize_execution_domain(raw)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, DEFAULT_WORLD_NODE_STATUS),
        ("", DEFAULT_WORLD_NODE_STATUS),
        ("   ", DEFAULT_WORLD_NODE_STATUS),
        (" RUNNING ", "running"),
        ("Paused", "paused"),
    ],
)
def test_normalize_world_node_status_defaults_and_lowercases(raw: object, expected: str) -> None:
    assert _normalize_world_node_status(raw) == expected


@pytest.mark.parametrize("raw", ["ready", object()])
def test_normalize_world_node_status_rejects_unknown_values(raw: object) -> None:
    with pytest.raises(ValueError, match="unknown world node status"):
        _normalize_world_node_status(raw)  # type: ignore[arg-type]
