import pytest
from qmtl.sdk import StreamInput, QuestDBLoader, QuestDBRecorder


def test_questdb_table_defaults_to_node_id():
    stream = StreamInput(
        interval="60s",
        period=1,
        history_provider=QuestDBLoader("db"),
        event_recorder=QuestDBRecorder("db"),
    )
    assert stream.history_provider.table == stream.node_id
    assert stream.event_recorder.table == stream.node_id


def test_questdb_explicit_table_override():
    loader = QuestDBLoader("db", table="t")
    recorder = QuestDBRecorder("db", table="t")
    stream = StreamInput(
        interval="60s",
        period=1,
        history_provider=loader,
        event_recorder=recorder,
    )
    assert loader.table == "t"
    assert recorder.table == "t"

