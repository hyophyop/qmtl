from qmtl.schema import SchemaRegistryClient


def test_register_latest_and_compatibility():
    reg = SchemaRegistryClient()
    s1 = reg.register("prices", "{\"a\": 1}")
    assert s1.id > 0 and s1.version == 1
    assert reg.latest("prices").id == s1.id
    assert SchemaRegistryClient.is_backward_compatible("{\"a\": 1}", "{\"a\": 1, \"b\": 2}")
    assert not SchemaRegistryClient.is_backward_compatible("{\"a\": 1, \"b\": 2}", "{\"a\": 1}")

