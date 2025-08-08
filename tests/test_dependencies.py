import tomllib

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
    with open("pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    deps = set(dep.split("[")[0] for dep in data["project"]["dependencies"])
    missing = EXPECTED - deps
    assert not missing, f"Missing dependencies: {missing}"
