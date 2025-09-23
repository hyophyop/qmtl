from qmtl.foundation.kafka.schema_producer import SchemaAwareProducer


class DummyProducer:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict]] = []

    def produce(self, topic: str, value):
        self.records.append((topic, value))

    def flush(self):
        return None


def test_schema_producer_envelope_and_register():
    inner = DummyProducer()
    sap = SchemaAwareProducer(inner)
    sap.produce("ticks", {"p": 1}, schema="{\"p\": 0}")
    assert inner.records and inner.records[-1][0] == "ticks"
    out = inner.records[-1][1]
    assert "schema_id" in out and out["payload"] == {"p": 1}
    # Subsequent publish does not require schema
    sap.produce("ticks", {"p": 2})
    assert inner.records[-1][1]["schema_id"] == out["schema_id"]

