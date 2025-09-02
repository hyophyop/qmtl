from qmtl.schema.registry import SchemaRegistryClient


def test_register_and_latest_and_compatibility():
    reg = SchemaRegistryClient()
    s1 = reg.register("topic-a", "{\"a\": 1}")
    assert s1.id == 1 and s1.version == 1
    assert reg.latest("topic-a").id == s1.id
    # Backward compatible if new schema adds fields
    assert SchemaRegistryClient.is_backward_compatible("{\"a\": 1}", "{\"a\": 1, \"b\": 2}")
    # Not compatible if required key is removed
    assert not SchemaRegistryClient.is_backward_compatible("{\"a\": 1, \"b\": 2}", "{\"a\": 1}")

