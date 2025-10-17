from qmtl.runtime.pipeline import Pipeline
from qmtl.runtime.sdk import ProcessingNode, StreamInput
from qmtl.runtime.sdk.runner import Runner


class DummyProducer:
    def __init__(self):
        self.messages = []

    def produce(self, topic, value):
        self.messages.append((topic, value))

    def flush(self):
        pass


def test_pipeline_feed_emits_contract_payloads(monkeypatch):
    src = StreamInput(interval="1s", period=1)

    def mul2(view):
        _, val = view[src][1].latest()
        return val * 2

    n1 = ProcessingNode(input=src, compute_fn=mul2, name="n1", interval="1s", period=1)

    def add1(view):
        _, val = view[n1][1].latest()
        return val + 1

    n2 = ProcessingNode(input=n1, compute_fn=add1, name="n2", interval="1s", period=1)

    producer = DummyProducer()
    n1.kafka_topic = "n1"
    n2.kafka_topic = "n2"

    calls = []
    original_feed = Runner.feed_queue_data

    def spy(node, queue_id, interval, timestamp, payload, *, on_missing="skip"):
        calls.append((node.name, queue_id, interval, timestamp, payload, on_missing))
        return original_feed(node, queue_id, interval, timestamp, payload, on_missing=on_missing)

    monkeypatch.setattr(Runner, "feed_queue_data", spy)

    pipe = Pipeline([src, n1, n2], producer=producer)
    pipe.feed(src, 1, 10)

    assert [topic for topic, _ in producer.messages] == ["n1", "n2"]
    assert [payload["payload"] for _, payload in producer.messages] == [20, 21]
    assert {(call[0], call[1]) for call in calls} == {("n1", src.node_id), ("n2", n1.node_id)}
    assert n2.compute_fn(n2.cache.view()) == 21


def test_execute_false_pass_through(monkeypatch):
    src = StreamInput(interval="1s", period=1)
    n1 = ProcessingNode(input=src, compute_fn=lambda view: None, name="n1", interval="1s", period=1)
    n1.execute = False
    n2 = ProcessingNode(
        input=n1,
        compute_fn=lambda view: view[n1][1].latest()[1] + 5,
        name="n2",
        interval="1s",
        period=1,
    )

    calls = []
    original_feed = Runner.feed_queue_data

    def spy(node, queue_id, interval, timestamp, payload, *, on_missing="skip"):
        calls.append((node.name, payload, on_missing))
        return original_feed(node, queue_id, interval, timestamp, payload, on_missing=on_missing)

    monkeypatch.setattr(Runner, "feed_queue_data", spy)

    pipe = Pipeline([src, n1, n2])
    pipe.feed(n1, 1, 2)

    assert calls == [("n2", 2, "skip")]
    assert n2.compute_fn(n2.cache.view()) == 7


def test_pipeline_feed_passes_on_missing(monkeypatch):
    src = StreamInput(interval="1s", period=1)

    def identity(view):
        _, val = view[src][1].latest()
        return val

    downstream = ProcessingNode(input=src, compute_fn=identity, name="down", interval="1s", period=1)

    captured = []
    original_feed = Runner.feed_queue_data

    def spy(node, queue_id, interval, timestamp, payload, *, on_missing="skip"):
        captured.append(on_missing)
        return original_feed(node, queue_id, interval, timestamp, payload, on_missing=on_missing)

    monkeypatch.setattr(Runner, "feed_queue_data", spy)

    pipe = Pipeline([src, downstream])
    pipe.feed(src, 1, 5, on_missing="fail")

    assert captured == ["fail"]
    assert downstream.compute_fn(downstream.cache.view()) == 5
