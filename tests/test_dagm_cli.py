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
    assert '"q": 1' in out

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

