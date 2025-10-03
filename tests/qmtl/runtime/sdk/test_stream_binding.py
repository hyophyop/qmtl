import pytest
from qmtl.runtime.sdk import (
    AugmentedHistoryProvider,
    QuestDBBackend,
    QuestDBHistoryProvider,
    QuestDBRecorder,
    StreamInput,
    EventRecorderService,
)


def test_questdb_table_defaults_to_node_id():
    stream = StreamInput(
        interval="60s",
        period=1,
        history_provider=QuestDBHistoryProvider("db"),
        event_service=EventRecorderService(QuestDBRecorder("db")),
    )
    assert stream.history_provider.table == stream.node_id
    assert stream.event_recorder.table == stream.node_id


def test_questdb_explicit_table_override():
    loader = QuestDBHistoryProvider("db", table="t")
    recorder = QuestDBRecorder("db", table="t")
    stream = StreamInput(
        interval="60s",
        period=1,
        history_provider=loader,
        event_service=EventRecorderService(recorder),
    )
    assert loader.table == "t"
    assert recorder.table == "t"


def test_stream_input_wraps_backend():
    backend = QuestDBBackend("db")
    stream = StreamInput(interval="60s", period=1, history_provider=backend)
    provider = stream.history_provider
    assert isinstance(provider, AugmentedHistoryProvider)
    assert provider.backend is backend
    assert backend.table == stream.node_id
