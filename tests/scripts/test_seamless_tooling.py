from __future__ import annotations

from pathlib import Path

import pytest

from scripts import inject_sla_violation, lease_recover


class _StubCoordinator:
    def __init__(self) -> None:
        self.fail_calls: list[tuple[str, str]] = []
        self.complete_calls: list[str] = []

    async def fail(self, lease, reason: str) -> None:  # pragma: no cover - simple container
        self.fail_calls.append((lease.key, reason))

    async def complete(self, lease) -> None:
        self.complete_calls.append(lease.key)


@pytest.mark.asyncio
async def test_recover_leases_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    coordinator = _StubCoordinator()
    specs = [lease_recover.LeaseSpec.parse("node:token"), lease_recover.LeaseSpec.parse("other:token2")]
    summary = await lease_recover.recover_leases(
        specs,
        coordinator=coordinator,
        action="fail",
        reason="stuck",
    )
    assert summary.processed == 2
    assert summary.released == 2
    assert summary.skipped == 0
    assert summary.errors == ()
    assert coordinator.fail_calls == [("node", "stuck"), ("other", "stuck")]


@pytest.mark.asyncio
async def test_recover_leases_missing_token() -> None:
    coordinator = _StubCoordinator()
    specs = [lease_recover.LeaseSpec.parse("node"), lease_recover.LeaseSpec.parse("node2:token")]
    summary = await lease_recover.recover_leases(specs, coordinator=coordinator)
    assert summary.processed == 2
    assert summary.released == 1
    assert summary.skipped == 1
    assert "missing token" in summary.errors[0]


def test_inject_samples_generates_metrics(tmp_path: Path) -> None:
    output_file = tmp_path / "metrics.txt"
    text = inject_sla_violation.inject_samples(
        node_id="demo",
        phases=("total",),
        duration_seconds=42.0,
        repetitions=3,
        output_path=output_file,
    )
    assert "seamless_sla_deadline_seconds" in text
    assert output_file.read_text() == text


def test_lease_spec_parse_round_trip() -> None:
    spec = lease_recover.LeaseSpec.parse("key:token")
    assert spec.key == "key"
    assert spec.token == "token"
    with pytest.raises(ValueError):
        lease_recover.LeaseSpec.parse("")
