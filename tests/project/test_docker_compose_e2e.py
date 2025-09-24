from pathlib import Path

import yaml

def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("Could not locate repository root from test path")


COMPOSE_FILE = _repo_root() / "tests" / "docker-compose.e2e.yml"


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
        "dagmanager",
    }
    assert expected.issubset(services.keys())
