from pathlib import Path
import yaml

COMPOSE_FILE = Path(__file__).parent.parent / "docker-compose.sdk.yml"


def test_sdk_compose_services():
    data = yaml.safe_load(COMPOSE_FILE.read_text())
    services = set(data.get("services", {}).keys())
    expected = {"redis", "postgres", "neo4j", "gateway", "dag-manager"}
    assert expected.issubset(services)
