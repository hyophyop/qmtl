from qmtl.services.gateway.controlbus_codec import encode, decode, PROTO_CONTENT_TYPE
from qmtl.services.gateway.controlbus_consumer import ControlBusConsumer


class _Msg:
    def __init__(self, value: bytes, headers: list[tuple[str, bytes]]):
        self.value = value
        self.headers = headers
        self.key = b"k"
        self.topic = "activation"
        self.timestamp = 0


def test_codec_roundtrip_proto_placeholder():
    evt = {"type": "ActivationUpdated", "data": {"x": 1}}
    payload, headers = encode(evt, use_proto=True)
    # Content type header set
    assert dict(headers).get("content_type") == PROTO_CONTENT_TYPE.encode()
    # Decoder returns original dict
    assert decode(payload, {"content_type": PROTO_CONTENT_TYPE}) == evt


def test_consumer_parse_kafka_message_proto_path():
    c = ControlBusConsumer(brokers=None, topics=["t"], group="g")
    evt = {"type": "PolicyUpdated", "data": {"y": 2}}
    payload, headers = encode(evt, use_proto=True)
    msg = _Msg(payload, headers)
    out = c._parse_kafka_message(msg)
    assert out.data == evt


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

