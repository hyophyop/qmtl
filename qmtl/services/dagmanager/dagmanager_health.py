from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from neo4j import Driver


def get_health(driver: "Driver" | None = None) -> dict[str, str]:
    """Return health information about DAG Manager and dependencies."""
    neo4j_status = "unknown"
    if driver is not None:
        try:
            with driver.session() as session:
                session.run("RETURN 1")
            neo4j_status = "ok"
        except Exception:
            neo4j_status = "error"
    return {
        "status": "ok" if neo4j_status == "ok" else "degraded",
        "neo4j": neo4j_status,
        "dagmanager": "running",
    }
