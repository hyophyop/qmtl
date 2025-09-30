import asyncio
import pytest

from qmtl.runtime.sdk import ProcessingNode, StreamInput, Strategy, Runner

class DummyStrategy(Strategy):
    def __init__(self, nodes):
        super().__init__()
        self.add_nodes(nodes)
    def setup(self):
        pass


@pytest.mark.asyncio
async def test_single_node_consumption(monkeypatch):
    calls = []

    def compute(view):
        calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=compute, name="n1", interval="60s", period=2)
    node.kafka_topic = "t1"
    strategy = DummyStrategy([src, node])

    stop_event = asyncio.Event()

    async def fake_consume(n, *, consumer_factory, bootstrap_servers, stop_event):
        Runner.feed_queue_data(n, n.kafka_topic, 60, 60, {"v": 1})
        Runner.feed_queue_data(n, n.kafka_topic, 60, 120, {"v": 2})
        stop_event.set()

    monkeypatch.setattr(Runner, "_consume_node", fake_consume)
    tasks = Runner.spawn_consumer_tasks(
        strategy, bootstrap_servers="kafka", stop_event=stop_event
    )
    await asyncio.gather(*tasks)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_multi_node_consumption(monkeypatch):
    calls = []

    def compute1(view):
        calls.append("n1")

    def compute2(view):
        calls.append("n2")

    src1 = StreamInput(interval="60s", period=2)
    node1 = ProcessingNode(input=src1, compute_fn=compute1, name="n1", interval="60s", period=2)
    node1.kafka_topic = "t1"

    src2 = StreamInput(interval="60s", period=2)
    node2 = ProcessingNode(input=src2, compute_fn=compute2, name="n2", interval="60s", period=2)
    node2.kafka_topic = "t2"

    strategy = DummyStrategy([src1, node1, src2, node2])

    stop_event = asyncio.Event()
    counter = {"c": 0}

    async def fake_consume(n, *, consumer_factory, bootstrap_servers, stop_event):
        Runner.feed_queue_data(n, n.kafka_topic, 60, 60, {"v": 1})
        Runner.feed_queue_data(n, n.kafka_topic, 60, 120, {"v": 2})
        counter["c"] += 1
        if counter["c"] == 2:
            stop_event.set()

    monkeypatch.setattr(Runner, "_consume_node", fake_consume)
    tasks = Runner.spawn_consumer_tasks(
        strategy, bootstrap_servers="kafka", stop_event=stop_event
    )
    await asyncio.gather(*tasks)

    assert calls.count("n1") == 1
    assert calls.count("n2") == 1

