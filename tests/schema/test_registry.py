from qmtl.schema import SchemaRegistryClient


def test_register_and_latest():
    reg = SchemaRegistryClient()
    s1 = reg.register("prices", "{\"a\": 1}")
    assert s1.id > 0 and s1.version == 1
    assert reg.latest("prices").id == s1.id

