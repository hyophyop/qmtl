import pytest

from qmtl.foundation.config import DeploymentProfile
from qmtl.services.gateway import cli
from qmtl.services.gateway.config import GatewayConfig
from qmtl.services.gateway.redis_client import InMemoryRedis


def test_resolve_redis_requires_dsn_in_prod(caplog: pytest.LogCaptureFixture) -> None:
    config = GatewayConfig(redis_dsn=None)

    with pytest.raises(SystemExit):
        cli._resolve_redis(config, profile=DeploymentProfile.PROD)

    assert "gateway.redis_dsn" in caplog.text


def test_resolve_redis_dev_fallback() -> None:
    config = GatewayConfig(redis_dsn=None)

    redis_client = cli._resolve_redis(config, profile=DeploymentProfile.DEV)

    assert isinstance(redis_client, InMemoryRedis)


def test_enforce_database_profile_requires_postgres_backend(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = GatewayConfig(database_backend="sqlite", database_dsn=":memory:")

    with pytest.raises(SystemExit):
        cli._enforce_database_profile(config, profile=DeploymentProfile.PROD)

    assert "gateway.database_backend=postgres" in caplog.text


def test_enforce_database_profile_requires_dsn(caplog: pytest.LogCaptureFixture) -> None:
    config = GatewayConfig(database_backend="postgres", database_dsn=None)

    with pytest.raises(SystemExit):
        cli._enforce_database_profile(config, profile=DeploymentProfile.PROD)

    assert "gateway.database_dsn" in caplog.text

