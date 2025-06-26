from __future__ import annotations

import argparse
import asyncio

import redis.asyncio as redis

from .api import create_app
from .config import GatewayConfig, load_gateway_config


async def _main(argv: list[str] | None = None) -> None:
    """Run the Gateway HTTP server."""
    parser = argparse.ArgumentParser(prog="qmtl-gateway")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument(
        "--redis-dsn",
        help="Redis connection DSN",
    )
    parser.add_argument("--database-dsn", help="Database connection DSN")
    parser.add_argument(
        "--database-backend",
        default="postgres",
        help="Database backend (postgres, memory)",
    )
    args = parser.parse_args(argv)

    config = GatewayConfig()
    if args.config:
        config = load_gateway_config(args.config)
    if args.redis_dsn:
        config.redis_dsn = args.redis_dsn
    if args.database_dsn:
        config.database_dsn = args.database_dsn
    if args.database_backend:
        config.database_backend = args.database_backend

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

    uvicorn.run(app, host=args.host, port=args.port)


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

