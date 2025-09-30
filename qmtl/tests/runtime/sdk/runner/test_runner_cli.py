import importlib
import sys

import httpx

from qmtl.runtime.sdk import runtime


def test_cli_execution(monkeypatch, gateway_mock):
    monkeypatch.setenv("QMTL_TEST_MODE", "1")
    from qmtl.runtime.sdk.cli import main
    from qmtl.runtime.sdk.runner import Runner
    from qmtl.runtime.sdk import StreamInput

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    gateway_mock(handler)

    calls = []

    async def dummy_load_history(self, start, end):
        calls.append((start, end))

    monkeypatch.setattr(StreamInput, "load_history", dummy_load_history)

    argv = [
        "qmtl.runtime.sdk",
        "run",
        "tests.sample_strategy:SampleStrategy",
        "--world-id",
        "w",
        "--gateway-url",
        "http://gw",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    assert calls == [(1, 2)]
    Runner.set_default_context(None)


def test_ray_flag_auto_set(monkeypatch):
    import qmtl.runtime.sdk.runner as runner_mod

    original_ray = sys.modules.get("ray")
    monkeypatch.delitem(sys.modules, "ray", raising=False)
    importlib.reload(runner_mod)
    assert not runner_mod.Runner.services().ray_executor.available

    class DummyModule:
        pass

    monkeypatch.setitem(sys.modules, "ray", DummyModule())
    importlib.reload(runner_mod)
    assert runner_mod.Runner.services().ray_executor.available

    if original_ray is None:
        monkeypatch.delitem(sys.modules, "ray", raising=False)
    else:
        monkeypatch.setitem(sys.modules, "ray", original_ray)
    importlib.reload(runner_mod)


def test_cli_disable_ray(monkeypatch):
    import qmtl.runtime.sdk.cli as cli_mod
    import qmtl.runtime.sdk.runner as runner_mod

    dummy_ray = object()
    monkeypatch.setattr(runner_mod.Runner.services().ray_executor, "_ray", dummy_ray, raising=False)
    runner_mod.Runner.services().ray_executor.set_disabled(False)
    monkeypatch.setattr(runtime, "NO_RAY", False)
    importlib.reload(cli_mod)

    argv = [
        "qmtl.runtime.sdk",
        "offline",
        "tests.sample_strategy:SampleStrategy",
        "--no-ray",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli_mod.main()
    assert runtime.NO_RAY
