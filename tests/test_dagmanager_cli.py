import json
import pytest

# Suppress unraisable exceptions surfaced by pytest when background resources
# (event loops/sockets) from third-party libs are cleaned up during tests.
pytestmark = [
    pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning'),
    pytest.mark.filterwarnings('ignore:unclosed <socket.socket[^>]*>'),
    pytest.mark.filterwarnings('ignore:unclosed event loop'),
]
from qmtl.dagmanager.cli import main
from qmtl.proto import dagmanager_pb2, dagmanager_pb2_grpc
import grpc
from qmtl.dagmanager.kafka_admin import partition_key, compute_key

class DummyChannel:
    async def close(self):
        pass


class DummyRpcError(grpc.RpcError):
    def __init__(self, msg="boom"):
        super().__init__()
        self._msg = msg

    def __str__(self) -> str:  # pragma: no cover - simple string
        return self._msg

def test_cli_diff_dry_run(tmp_path, capsys):
    dag = {
        "nodes": [
            {
                "node_id": "n1",
                "code_hash": "c",
                "config_hash": "cfg",
                "schema_hash": "s",
                "schema_compat_id": "s-major",
                "params": {},
                "dependencies": [],
            }
        ]
    }
    path = tmp_path / "dag.json"
    path.write_text(json.dumps(dag))
    main(["diff", "--file", str(path), "--dry_run"])
    out = capsys.readouterr().out
    assert "n1" in out

def test_cli_queue_stats(monkeypatch, capsys):
    class Stub:
        def __init__(self, channel):
            pass
        async def GetQueueStats(self, request):
            return dagmanager_pb2.QueueStats(sizes={"q": 1})

    captured = {}
    def fake_channel(target):
        captured["target"] = target
        return DummyChannel()

    monkeypatch.setattr(dagmanager_pb2_grpc, "AdminServiceStub", Stub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", fake_channel)
    main(["queue-stats"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data == {"q": 1}
    assert captured["target"] == "localhost:50051"

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


## NOTE: Duplicate test removed; the following test covers redo-diff path.


def test_cli_redo_diff(monkeypatch, tmp_path, capsys):
    called = {}

    class Stub:
        def __init__(self, channel):
            pass

        async def RedoDiff(self, request):
            called["sentinel"] = request.sentinel_id
            return dagmanager_pb2.DiffResult(
                queue_map={
                    partition_key(
                        "q",
                        None,
                        None,
                        compute_key=compute_key("q"),
                    ): "t"
                },
                sentinel_id=request.sentinel_id,
                version="v2025",
            )

    monkeypatch.setattr(dagmanager_pb2_grpc, "AdminServiceStub", Stub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())
    path = tmp_path / "dag.json"
    path.write_text("{}")
    main(["redo-diff", "--sentinel", "v1", "--file", str(path)])
    out = capsys.readouterr().out
    assert called["sentinel"] == "v1"
    key = partition_key("q", None, None, compute_key=compute_key("q"))
    assert f'"{key}": "t"' in out
    assert '"version": "v2025"' in out


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


def test_cli_diff_file_error(capsys):
    with pytest.raises(SystemExit):
        main(["diff", "--file", "missing.json", "--dry_run"])
    err = capsys.readouterr().err
    assert "Failed to read file" in err


def test_cli_redo_diff_file_error(capsys):
    with pytest.raises(SystemExit):
        main(["redo-diff", "--sentinel", "s", "--file", "missing.json"])
    err = capsys.readouterr().err
    assert "Failed to read file" in err


def test_cli_diff_grpc_error(monkeypatch, tmp_path, capsys):
    path = tmp_path / "dag.json"
    path.write_text("{}")

    class DummyClient:
        def __init__(self, target):
            pass

        async def diff(self, strategy_id, dag_json, **_kwargs):
            raise DummyRpcError("fail")

        async def close(self):
            pass

    monkeypatch.setattr("qmtl.dagmanager.cli.DagManagerClient", DummyClient)
    with pytest.raises(SystemExit):
        main(["diff", "--file", str(path)])
    err = capsys.readouterr().err
    assert "gRPC error" in err


def test_cli_queue_stats_grpc_error(monkeypatch, capsys):
    class Stub:
        def __init__(self, channel):
            pass

        async def GetQueueStats(self, request):
            raise DummyRpcError("fail")

    monkeypatch.setattr(dagmanager_pb2_grpc, "AdminServiceStub", Stub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())
    with pytest.raises(SystemExit):
        main(["queue-stats"])
    err = capsys.readouterr().err
    assert "gRPC error" in err


def test_cli_snapshot_freeze_and_verify(tmp_path, capsys):
    dag = {
        "nodes": [
            {
                "node_id": "n1",
                "code_hash": "c",
                "config_hash": "cfg",
                "schema_hash": "s",
                "schema_compat_id": "s-major",
                "params": {},
                "dependencies": [],
            }
        ]
    }
    dag_path = tmp_path / "dag.json"
    dag_path.write_text(json.dumps(dag))
    snap_path = tmp_path / "snap.json"
    main(["snapshot", "--file", str(dag_path), "--freeze", "--snapshot", str(snap_path)])
    assert snap_path.exists()
    main(["snapshot", "--file", str(dag_path), "--verify", "--snapshot", str(snap_path)])
    out = capsys.readouterr().out
    assert "Snapshot OK" in out


def test_cli_snapshot_verify_fail(tmp_path, capsys):
    dag_path = tmp_path / "dag.json"
    dag_path.write_text("{}")
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps({"dag_hash": "bad", "dag": {}}))
    with pytest.raises(SystemExit):
        main(["snapshot", "--file", str(dag_path), "--verify", "--snapshot", str(snap_path)])
    err = capsys.readouterr().err
    assert "Snapshot mismatch" in err
