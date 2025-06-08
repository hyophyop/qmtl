from __future__ import annotations

import argparse
import asyncio

import redis.asyncio as redis

from .api import create_app, PostgresDatabase


def main(argv: list[str] | None = None) -> None:
    """Run the Gateway HTTP server."""
    parser = argparse.ArgumentParser(prog="qmtl-gateway")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument(
        "--redis-dsn",
        default="redis://localhost:6379",
        help="Redis connection DSN",
    )
    parser.add_argument(
        "--postgres-dsn",
        default="postgresql://localhost/qmtl",
        help="PostgreSQL connection DSN",
    )
    args = parser.parse_args(argv)

    redis_client = redis.from_url(args.redis_dsn, decode_responses=True)
    db = PostgresDatabase(args.postgres_dsn)
    # Connect database if possible; ignore failures to ease testing
    try:
        asyncio.run(db.connect())
    except Exception:
        pass

    app = create_app(redis_client=redis_client, database=db)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

