SCHEMA_QUERIES = [
    "CREATE CONSTRAINT compute_pk IF NOT EXISTS ON (c:ComputeNode) ASSERT c.node_id IS UNIQUE",
    "CREATE INDEX kafka_topic IF NOT EXISTS FOR (q:Queue) ON (q.topic)",
]


def get_schema_queries() -> list[str]:
    """Return Cypher statements needed to initialize Neo4j schema."""
    return SCHEMA_QUERIES.copy()


if __name__ == "__main__":  # pragma: no cover - manual execution
    from neo4j import GraphDatabase
    import argparse

    parser = argparse.ArgumentParser(description="Initialize Neo4j schema")
    parser.add_argument("uri")
    parser.add_argument("user")
    parser.add_argument("password")
    args = parser.parse_args()

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    with driver.session() as session:
        for stmt in SCHEMA_QUERIES:
            session.run(stmt)
    driver.close()
