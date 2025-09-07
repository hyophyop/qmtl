from .neo4j_export import connect


SCHEMA_QUERIES = [
    # Uniqueness and lookup for core access paths
    "CREATE CONSTRAINT compute_pk IF NOT EXISTS ON (c:ComputeNode) ASSERT c.node_id IS UNIQUE",
    "CREATE INDEX kafka_topic IF NOT EXISTS FOR (q:Queue) ON (q.topic)",
    # Performance-focused indexes for common queries
    # Tag-based queue lookups: any/all membership checks over c.tags
    "CREATE INDEX compute_tags IF NOT EXISTS FOR (c:ComputeNode) ON (c.tags)",
    # Interval filtered lookups on queues
    "CREATE INDEX queue_interval IF NOT EXISTS FOR (q:Queue) ON (q.interval)",
    # Buffering window scans for GC/monitoring
    "CREATE INDEX compute_buffering_since IF NOT EXISTS FOR (c:ComputeNode) ON (c.buffering_since)",
]


def get_schema_queries() -> list[str]:
    """Return Cypher statements needed to initialize Neo4j schema."""
    return SCHEMA_QUERIES.copy()


def apply_schema(driver) -> None:
    """Execute initialization statements using *driver*."""
    with driver.session() as session:
        for stmt in get_schema_queries():
            session.run(stmt)


def init_schema(uri: str, user: str, password: str) -> None:
    """Connect to Neo4j and apply schema constraints and indexes."""
    driver = connect(uri, user, password)
    try:
        apply_schema(driver)
    finally:
        driver.close()
