from qmtl.gateway.controlbus_codec import encode, decode, PROTO_CONTENT_TYPE
from qmtl.gateway.controlbus_consumer import ControlBusConsumer


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

