from qmtl.dagmanager.config import DagManagerConfig


def test_dagmanager_config_custom_values() -> None:
    cfg = DagManagerConfig(
        neo4j_dsn="bolt://db:7687",
        neo4j_user="neo4j",
        neo4j_password="pw",
        kafka_dsn="localhost:9092",
        kafka_breaker_threshold=5,
        kafka_breaker_timeout=2.5,
        neo4j_breaker_threshold=4,
        neo4j_breaker_timeout=1.5,
    )
    assert cfg.neo4j_dsn == "bolt://db:7687"
    assert cfg.kafka_dsn == "localhost:9092"
    assert cfg.kafka_breaker_threshold == 5
    assert cfg.kafka_breaker_timeout == 2.5
    assert cfg.neo4j_breaker_threshold == 4
    assert cfg.neo4j_breaker_timeout == 1.5


def test_dagmanager_config_defaults() -> None:
    cfg = DagManagerConfig()
    assert cfg.neo4j_dsn is None
    assert cfg.kafka_dsn is None
    assert cfg.kafka_breaker_threshold == 3
    assert cfg.kafka_breaker_timeout == 60.0
    assert cfg.neo4j_breaker_threshold == 3
    assert cfg.neo4j_breaker_timeout == 60.0

