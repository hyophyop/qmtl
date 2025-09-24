from qmtl.services.dagmanager.neo4j_export import export_schema

class FakeSession:
    def __init__(self):
        self.run_calls = []

    def run(self, query):
        self.run_calls.append(query)
        if "CONSTRAINTS" in query:
            return [{"createStatement": "CREATE CONSTRAINT c"}]
        return [{"createStatement": "CREATE INDEX i"}]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

class FakeDriver:
    def __init__(self):
        self.session_obj = FakeSession()

    def session(self):
        return self.session_obj

    def close(self):
        pass


def test_export_schema_collects_statements():
    driver = FakeDriver()
    stmts = export_schema(driver)
    assert stmts == ["CREATE CONSTRAINT c", "CREATE INDEX i"]
    assert len(driver.session_obj.run_calls) == 2

