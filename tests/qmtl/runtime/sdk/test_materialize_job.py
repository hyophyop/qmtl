from __future__ import annotations

import pandas as pd
import pytest

from qmtl.runtime.sdk.conformance import ConformanceReport
from qmtl.runtime.sdk.materialize_job import MaterializeReport, MaterializeSeamlessJob
from qmtl.runtime.sdk.seamless_data_provider import SeamlessFetchMetadata, SeamlessFetchResult


class _StubProvider:
    def __init__(self, *, fingerprint: str | None = None, live_feed: object | None = None):
        self.live_feed = live_feed
        self._fingerprint = fingerprint
        self._report = ConformanceReport()

    @property
    def last_conformance_report(self) -> ConformanceReport:
        return self._report

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int, **_: object) -> SeamlessFetchResult:
        frame = pd.DataFrame({"ts": [start, end]})
        metadata = SeamlessFetchMetadata(
            node_id=node_id,
            interval=interval,
            requested_range=(start, end),
            rows=len(frame),
            coverage_bounds=(start, end),
            conformance_flags=dict(self._report.flags_counts),
            conformance_warnings=self._report.warnings,
            dataset_fingerprint=self._fingerprint,
        )
        return SeamlessFetchResult(frame, metadata)


@pytest.mark.asyncio
async def test_materialize_job_returns_report(tmp_path) -> None:
    provider = _StubProvider(fingerprint="v1:demo")
    job = MaterializeSeamlessJob(
        provider=provider,
        start=0,
        end=10,
        interval=5,
        contract_version="v1",
        checkpoint_dir=tmp_path,
        retention_class="research-short",
        retention_ttl_seconds=3600,
        priority="low",
        max_attempts=2,
    )

    report = await job.run()

    assert isinstance(report, MaterializeReport)
    assert report.dataset_fingerprint == "v1:demo"
    assert report.coverage_bounds == (0, 10)
    assert report.requested_range == (0, 10)
    assert report.contract_version == "v1"
    assert report.retention_class == "research-short"
    assert report.retention_ttl_seconds == 3600
    assert report.priority == "low"
    assert report.checkpoint_key.startswith("materialize:")
    assert report.resumed is False
    assert report.attempts == 1


@pytest.mark.asyncio
async def test_materialize_job_requires_live_when_flagged() -> None:
    provider = _StubProvider(live_feed=None)
    job = MaterializeSeamlessJob(provider=provider, start=0, end=1, interval=1, require_live=True)

    with pytest.raises(ValueError):
        await job.run()


@pytest.mark.asyncio
async def test_materialize_job_contract_version_mismatch() -> None:
    provider = _StubProvider(fingerprint="v1:data")
    job = MaterializeSeamlessJob(provider=provider, start=0, end=1, interval=1, contract_version="v2")

    with pytest.raises(ValueError):
        await job.run()


@pytest.mark.asyncio
async def test_materialize_job_resume(tmp_path) -> None:
    provider = _StubProvider(fingerprint="v1:demo")
    job = MaterializeSeamlessJob(
        provider=provider,
        start=0,
        end=2,
        interval=1,
        contract_version="v1",
        checkpoint_dir=tmp_path,
    )

    first = await job.run()
    second = await job.run()

    assert first.checkpoint_key == second.checkpoint_key
    assert second.resumed is True
    assert second.dataset_fingerprint == "v1:demo"


class _FlakyProvider(_StubProvider):
    def __init__(self, fail_times: int, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._remaining = fail_times

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int, **_: object) -> SeamlessFetchResult:
        if self._remaining > 0:
            self._remaining -= 1
            raise RuntimeError("flaky")
        return await super().fetch(start, end, node_id=node_id, interval=interval)


@pytest.mark.asyncio
async def test_materialize_job_retries() -> None:
    provider = _FlakyProvider(fail_times=1, fingerprint="v1:demo")
    job = MaterializeSeamlessJob(provider=provider, start=0, end=1, interval=1, contract_version="v1", max_attempts=2)

    report = await job.run()

    assert report.attempts == 2
