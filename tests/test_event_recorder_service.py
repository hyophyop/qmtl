import asyncio
from qmtl.sdk import SourceNode
from qmtl.sdk.event_recorder_service import EventRecorderService
from qmtl.sdk.data_io import EventRecorder


class DummyRecorder(EventRecorder):
    def __init__(self):
        self.records = []

    async def persist(self, node_id: str, interval: int, timestamp: int, payload):
        self.records.append((node_id, interval, timestamp, payload))


def test_event_recorder_service_invocation():
    recorder = DummyRecorder()
    service = EventRecorderService(recorder)
    node = SourceNode(interval="1s", period=1, event_recorder_service=service)
    node.feed("up", 1, 0, {"v": 1})
    assert recorder.records == [(node.node_id, 1, 0, {"v": 1})]
