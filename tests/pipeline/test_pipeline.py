import pytest

from qmtl.pipeline import Pipeline
from qmtl.sdk import ProcessingNode, StreamInput


class DummyProducer:
    def __init__(self):
        self.messages = []

    def produce(self, topic, value):
        self.messages.append((topic, value))

    def flush(self):
        pass


def test_basic_flow():
    src = StreamInput(interval=1, period=1)

    def mul2(view):
        ts, val = view[src][1].latest()
        return val * 2

    n1 = ProcessingNode(input=src, compute_fn=mul2, name="n1", interval=1, period=1)

    def add1(view):
        ts, val = view[n1][1].latest()
        return val + 1

    n2 = ProcessingNode(input=n1, compute_fn=add1, name="n2", interval=1, period=1)

    prod = DummyProducer()
    n1.queue_topic = "n1"
    n2.queue_topic = "n2"

    pipe = Pipeline([src, n1, n2], producer=prod)

    pipe.feed(src, 1, 10)

    assert prod.messages[0][0] == "n1"
    assert prod.messages[1][0] == "n2"
    assert prod.messages[1][1]["payload"] == 21
    assert n2.compute_fn(n2.cache.view()) == 21


def test_execute_false_pass_through():
    src = StreamInput(interval=1, period=1)
    n1 = ProcessingNode(input=src, compute_fn=lambda v: None, name="n1", interval=1, period=1)
    n1.execute = False
    n2 = ProcessingNode(input=n1, compute_fn=lambda v: v[n1][1].latest()[1] + 5, name="n2", interval=1, period=1)

    pipe = Pipeline([src, n1, n2])

    # feed direct result through n1
    pipe.feed(n1, 1, 2)
    assert n2.compute_fn(n2.cache.view()) == 7
