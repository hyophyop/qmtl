from __future__ import annotations

import pytest

from qmtl.dagmanager import metrics
from qmtl.dagmanager.diff_service import DiffService

from .diff_fakes import FakeQueue, FakeRepo, FakeStream
from .diff_helpers import make_diff_request, reset_diff_metrics


@pytest.fixture
def fake_repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def fake_queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
def fake_stream() -> FakeStream:
    return FakeStream()


@pytest.fixture
def diff_service(fake_repo: FakeRepo, fake_queue: FakeQueue, fake_stream: FakeStream) -> DiffService:
    return DiffService(fake_repo, fake_queue, fake_stream)


@pytest.fixture
def make_request():
    return make_diff_request


@pytest.fixture
def diff_metrics():
    reset_diff_metrics()
    try:
        yield metrics
    finally:
        reset_diff_metrics()
