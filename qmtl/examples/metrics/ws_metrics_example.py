import asyncio

from qmtl.sdk import WebSocketClient, metrics


async def main() -> None:
    metrics.start_metrics_server(port=8000)
    client = WebSocketClient("ws://localhost:8000/ws")
    await client.start()
    await asyncio.sleep(5)  # Listen briefly
    await client.stop()
    print("Topics:", client.queue_topics)
    print("Weights:", client.sentinel_weights)
    print(metrics.collect_metrics())


if __name__ == "__main__":
    asyncio.run(main())
