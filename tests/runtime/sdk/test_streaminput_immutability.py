from __future__ import annotations

import pytest

from qmtl.runtime.sdk import StreamInput, EventRecorderService
from qmtl.runtime.io import QuestDBLoader, QuestDBRecorder


def test_streaminput_history_provider_is_immutable() -> None:
    stream = StreamInput(
        interval="60s",
        period=10,
        history_provider=QuestDBLoader("postgresql://localhost:8812/qdb"),
    )

    # Attempting to reassign should raise
    with pytest.raises(AttributeError):
        stream.history_provider = QuestDBLoader("postgresql://localhost:8812/qdb")  # type: ignore[attr-defined]


def test_streaminput_event_recorder_immutable_and_binds_stream() -> None:
    svc = EventRecorderService(QuestDBRecorder("postgresql://localhost:8812/qdb"))
    stream = StreamInput(
        interval="60s",
        period=10,
        event_service=svc,
    )

    # event_recorder must be present through the service
    assert stream.event_recorder is not None

    # Recorder should be bound to this stream (table defaults to node_id)
    assert stream.event_recorder.table == stream.node_id

    # Reassignment must be blocked
    with pytest.raises(AttributeError):
        stream.event_recorder = QuestDBRecorder("postgresql://localhost:8812/qdb")  # type: ignore[attr-defined]

