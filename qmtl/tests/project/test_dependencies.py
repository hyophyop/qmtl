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

def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("Could not locate repository root from test path")


def test_required_dependencies_present():
    qmtl_root = _repo_root()
    with open(qmtl_root / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    deps = set(dep.split("[")[0] for dep in data["project"]["dependencies"])
    missing = EXPECTED - deps
    assert not missing, f"Missing dependencies: {missing}"
