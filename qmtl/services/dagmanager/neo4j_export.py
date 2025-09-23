from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:  # pragma: no cover - for type checking only
    from neo4j import Driver


def export_schema(driver: "Driver") -> List[str]:
    """Return Cypher DDL statements for constraints and indexes."""
    statements: List[str] = []
    with driver.session() as session:
        result = session.run(
            "SHOW CONSTRAINTS YIELD createStatement RETURN createStatement"
        )
        statements.extend(r["createStatement"] for r in result)
        result = session.run(
            "SHOW INDEXES YIELD createStatement RETURN createStatement"
        )
        statements.extend(r["createStatement"] for r in result)
    return statements


def connect(uri: str, user: str, password: str) -> "Driver":
    """Open a Neo4j driver connection."""
    from neo4j import GraphDatabase  # pragma: no cover - external dep

    return GraphDatabase.driver(uri, auth=(user, password))


def export_to_file(driver: "Driver", path: str | Path) -> None:
    """Export schema to *path* as newline-separated Cypher statements."""
    stmts = export_schema(driver)
    Path(path).write_text("\n".join(stmts) + "\n")

