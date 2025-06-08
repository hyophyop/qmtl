from pathlib import Path

import yaml

COMPOSE_FILE = Path(__file__).with_name("docker-compose.e2e.yml")


def test_e2e_compose_services():
    data = yaml.safe_load(COMPOSE_FILE.read_text())
    services = data.get("services", {})
    expected = {
        "redis",
        "postgres",
        "neo4j",
        "zookeeper",
        "kafka",
        "gateway",
        "dag-manager",
    }
    assert expected.issubset(services.keys())

