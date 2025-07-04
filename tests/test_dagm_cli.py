import json
from io import StringIO
import sys
from qmtl.dagmanager.cli import main
from qmtl.proto import dagmanager_pb2, dagmanager_pb2_grpc
import grpc

class DummyChannel:
    async def close(self):
        pass

def test_cli_diff_dryrun(tmp_path, capsys):
    dag = {"nodes": [{"node_id": "n1", "code_hash": "c", "schema_hash": "s"}]}
    path = tmp_path / "dag.json"
    path.write_text(json.dumps(dag))
    main(["diff", "--file", str(path), "--dry-run"])
    out = capsys.readouterr().out
    assert "n1" in out

def test_cli_queue_stats(monkeypatch, capsys):
    class Stub:
        def __init__(self, channel):
            pass
        async def GetQueueStats(self, request):
            return dagmanager_pb2.QueueStats(sizes={"q": 1})
    monkeypatch.setattr(dagmanager_pb2_grpc, "AdminServiceStub", Stub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())
    main(["queue-stats"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data == {"q": 1}

def test_cli_gc(monkeypatch, capsys):
    called = {}
    class Stub:
        def __init__(self, channel):
            pass
        async def Cleanup(self, request):
            called["sentinel"] = request.strategy_id
            return dagmanager_pb2.CleanupResponse()
    monkeypatch.setattr(dagmanager_pb2_grpc, "AdminServiceStub", Stub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())
    main(["gc", "--sentinel", "s1"])
    assert called["sentinel"] == "s1"


def test_cli_redo_diff(monkeypatch, tmp_path, capsys):
    called = {}

    class Stub:
        def __init__(self, channel):
            pass

        async def RedoDiff(self, request):
            called["sentinel"] = request.sentinel_id
            return dagmanager_pb2.DiffResult(queue_map={"q": "t"}, sentinel_id=request.sentinel_id)

    monkeypatch.setattr(dagmanager_pb2_grpc, "AdminServiceStub", Stub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())
    path = tmp_path / "dag.json"
    path.write_text("{}")
    main(["redo-diff", "--sentinel", "v1", "--file", str(path)])
    out = capsys.readouterr().out
    assert called["sentinel"] == "v1"
    assert '"q": "t"' in out


def test_cli_redo_diff(monkeypatch, tmp_path, capsys):
    called = {}

    class Stub:
        def __init__(self, channel):
            pass

        async def RedoDiff(self, request):
            called["sentinel"] = request.sentinel_id
            return dagmanager_pb2.DiffResult(queue_map={"q": "t"}, sentinel_id=request.sentinel_id)

    monkeypatch.setattr(dagmanager_pb2_grpc, "AdminServiceStub", Stub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())
    path = tmp_path / "dag.json"
    path.write_text("{}")
    main(["redo-diff", "--sentinel", "v1", "--file", str(path)])
    out = capsys.readouterr().out
    assert called["sentinel"] == "v1"
    assert '"q": "t"' in out


def test_cli_export_schema(monkeypatch, tmp_path):
    captured = {}

    class DummyDriver:
        def close(self):
            captured["closed"] = True

    def fake_connect(uri, user, password):
        captured["uri"] = uri
        return DummyDriver()

    def fake_export(driver):
        captured["driver"] = driver
        return ["CREATE CONSTRAINT c"]

    monkeypatch.setattr("qmtl.dagmanager.cli.connect", fake_connect)
    monkeypatch.setattr("qmtl.dagmanager.cli.export_schema", fake_export)

    out = tmp_path / "schema.cql"
    main(["export-schema", "--uri", "bolt://db", "--out", str(out)])

    assert out.read_text().strip() == "CREATE CONSTRAINT c"
    assert captured["uri"] == "bolt://db"
    assert captured["closed"]

