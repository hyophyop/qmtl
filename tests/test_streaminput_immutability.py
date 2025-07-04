import pytest
from qmtl.sdk import StreamInput


def test_streaminput_dependencies_readonly():
    s = StreamInput(interval="1s", period=1)
    with pytest.raises(AttributeError):
        s.history_provider = object()
    with pytest.raises(AttributeError):
        s.event_recorder = object()
