from qmtl.services.gateway.controlbus_codec import decode, encode
from qmtl.services.gateway.controlbus_consumer import ControlBusConsumer


class _Msg:
    def __init__(self, value: bytes, headers: list[tuple[str, bytes]]):
        self.value = value
        self.headers = headers
        self.key = b"k"
        self.topic = "activation"
        self.timestamp = 0


def test_codec_roundtrip_json():
    evt = {"type": "ActivationUpdated", "data": {"x": 1}}
    payload, headers = encode(evt)
    assert headers == []
    assert decode(payload) == evt


def test_consumer_parse_kafka_message_json_cloudevent_extracts_data():
    c = ControlBusConsumer(brokers=None, topics=["t"], group="g")
    evt = {"type": "PolicyUpdated", "data": {"y": 2}}
    payload, headers = encode(evt)
    msg = _Msg(payload, headers)
    out = c._parse_kafka_message(msg)
    assert out.data == {"y": 2}


def test_consumer_parse_queue_event_etag_ts():
    c = ControlBusConsumer(brokers=None, topics=["queue"], group="g")
    evt = {
        "type": "QueueUpdated",
        "tags": ["x"],
        "interval": 60,
        "queues": [],
        "match_mode": "any",
        "version": 1,
        "etag": "q:x:60:1",
        "ts": "2020-01-01T00:00:00Z",
    }
    payload, headers = encode(evt)
    msg = _Msg(payload, headers)
    msg.topic = "queue"
    out = c._parse_kafka_message(msg)
    assert out.etag == "q:x:60:1"
    assert out.data["etag"] == "q:x:60:1"
    assert out.data["ts"] == "2020-01-01T00:00:00Z"
