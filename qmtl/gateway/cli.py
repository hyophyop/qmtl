from __future__ import annotations

import argparse
import asyncio

import redis.asyncio as redis

from .redis_client import InMemoryRedis

from .api import create_app
from .config import GatewayConfig
from ..config import load_config


async def _main(argv: list[str] | None = None) -> None:
    """Run the Gateway HTTP server."""
    parser = argparse.ArgumentParser(prog="qmtl gw")
    parser.add_argument("--config", help="Path to configuration file")
    args = parser.parse_args(argv)

    config = GatewayConfig()
    if args.config:
        config = load_config(args.config).gateway

    if config.offline:
        redis_client = InMemoryRedis()
    else:
        redis_client = redis.from_url(config.redis_dsn, decode_responses=True)
    app = create_app(
        redis_client=redis_client,
        database_backend=config.database_backend,
        database_dsn=config.database_dsn,
    )
    db = app.state.database
    if hasattr(db, "connect"):
        try:
            await db.connect()  # type: ignore[attr-defined]
        except Exception:
            pass

    import uvicorn

    try:
        uvicorn.run(app, host=config.host, port=config.port)
    finally:
        if hasattr(db, "close"):
            try:
                await db.close()  # type: ignore[attr-defined]
            except Exception:
                pass


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

