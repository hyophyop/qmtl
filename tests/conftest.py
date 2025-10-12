import pytest
import pytest_asyncio
import yaml

from qmtl.runtime.sdk import configuration as sdk_configuration
from qmtl.runtime.sdk import runtime
from qmtl.runtime.sdk.arrow_cache import reload_arrow_cache
from qmtl.runtime.sdk.runner import Runner

@pytest_asyncio.fixture
async def fake_redis():
    fakeredis_aioredis = pytest.importorskip(
        "fakeredis.aioredis",
        reason="fakeredis is required for Redis-backed runtime tests",
    )
    redis = fakeredis_aioredis.FakeRedis(decode_responses=True)
    try:
        yield redis
    finally:
        if hasattr(redis, "aclose"):
            await redis.aclose(close_connection_pool=True)
        else:
            await redis.close()


@pytest.fixture(autouse=True)
def _default_runner_context():
    context = {
        "execution_mode": "backtest",
        "clock": "virtual",
        "as_of": "2025-01-01T00:00:00Z",
        "dataset_fingerprint": "lake:blake3:test",
    }
    Runner.set_default_context(context)
    try:
        yield context
    finally:
        Runner.set_default_context(None)


@pytest.fixture
def configure_sdk(tmp_path, monkeypatch):
    """Write a temporary qmtl.yml and reload runtime/config caches."""

    def _apply(data: dict, *, filename: str = "qmtl.yml") -> str:
        cfg_path = tmp_path / filename
        cfg_path.write_text(yaml.safe_dump(data))
        monkeypatch.chdir(tmp_path)
        sdk_configuration.reset_runtime_config_cache()
        runtime.reload()
        reload_arrow_cache()
        return str(cfg_path)

    try:
        yield _apply
    finally:
        sdk_configuration.reset_runtime_config_cache()
        runtime.reload()
        reload_arrow_cache()
