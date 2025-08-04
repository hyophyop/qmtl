from qmtl.dagmanager.topic import topic_name, get_config, TopicConfig
from qmtl.dagmanager.kafka_admin import KafkaAdmin, TopicExistsError


class FakeAdmin:
    def __init__(self, topics=None):
        self.topics = topics or {}
        self.created = []

    def list_topics(self):
        return self.topics

    def create_topic(self, name, *, num_partitions, replication_factor, config=None):
        if name in self.topics:
            raise TopicExistsError
        self.created.append((name, num_partitions, replication_factor, config))
        self.topics[name] = config or {}


def test_topic_name_generation():
    existing = {"btc_Indicator_abcdef_v1"}
    name = topic_name(
        "btc",
        "Indicator",
        "abcdef123456",
        "v1",
        existing=existing,
    )
    assert name == "btc_Indicator_abcdef12_v1"
    sim = topic_name(
        "btc",
        "Indicator",
        "abcdef123456",
        "v1",
        dryrun=True,
    )
    assert sim.endswith("_sim")

def test_topic_config_values():
    config = get_config("raw")
    assert config == TopicConfig(partitions=3, replication_factor=3, retention_ms=7 * 24 * 60 * 60 * 1000)
    ind = get_config("indicator")
    assert ind == TopicConfig(partitions=1, replication_factor=2, retention_ms=30 * 24 * 60 * 60 * 1000)
    exec_config = get_config("trade_exec")
    assert exec_config == TopicConfig(partitions=1, replication_factor=3, retention_ms=90 * 24 * 60 * 60 * 1000)


def test_idempotent_topic_creation():
    admin = FakeAdmin({"exists": {}})
    wrapper = KafkaAdmin(admin)

    config = TopicConfig(1, 1, 1000)
    wrapper.create_topic_if_needed("exists", config)
    wrapper.create_topic_if_needed("new", config)

    assert len(admin.created) == 1
    name, parts, repl, conf = admin.created[0]
    assert name == "new"
    assert parts == 1
    assert repl == 1
    assert conf["retention.ms"] == "1000"
