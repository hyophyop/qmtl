import tomllib
from pathlib import Path

EXPECTED = {
    "numpy",
    "httpx",
    "fastapi",
    "uvicorn",
    "redis",
    "asyncpg",
    "aiosqlite",
    "websockets",
    "grpcio",
    "PyYAML",
}

def test_required_dependencies_present():
    project_root = Path(__file__).resolve().parents[1]
    with open(project_root / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    deps = set(dep.split("[")[0] for dep in data["project"]["dependencies"])
    missing = EXPECTED - deps
    assert not missing, f"Missing dependencies: {missing}"
