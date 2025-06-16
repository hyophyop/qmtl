import qmtl.sdk.runner as rmod
from qmtl.sdk import ProcessingNode, StreamInput


def test_node_feed_with_ray(monkeypatch):
    class DummyRay:
        def __init__(self):
            self.calls = []
            self.inited = False

        def is_initialized(self):
            return self.inited

        def init(self, ignore_reinit_error=True):
            self.inited = True

        def remote(self, fn):
            dummy = self

            class Wrapper:
                def remote(self, *args, **kwargs):
                    dummy.calls.append((fn, args, kwargs))

            return Wrapper()

    dummy_ray = DummyRay()

    monkeypatch.setattr(rmod, "ray", dummy_ray)
    monkeypatch.setattr(rmod.Runner, "_ray_available", True)

    calls = []

    def compute(view):
        calls.append(view)

    src = StreamInput(interval=60, period=2)
    node = ProcessingNode(input=src, compute_fn=compute, name="n", interval=60, period=2)

    node.feed("q", 60, 60, {"v": 1})
    node.feed("q", 60, 120, {"v": 2})

    assert len(dummy_ray.calls) == 1
    assert not calls


def test_node_feed_without_ray(monkeypatch):
    monkeypatch.setattr(rmod.Runner, "_ray_available", False)

    calls = []

    def compute(view):
        calls.append(view)

    src = StreamInput(interval=60, period=2)
    node = ProcessingNode(input=src, compute_fn=compute, name="n", interval=60, period=2)

    node.feed("q", 60, 60, {"v": 1})
    node.feed("q", 60, 120, {"v": 2})

    assert len(calls) == 1

