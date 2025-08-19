from qmtl.sdk import StreamInput
from qmtl.io import QuestDBLoader, QuestDBRecorder, BinanceFetcher


def test_binance_stream_components() -> None:
    fetcher = BinanceFetcher()
    stream = StreamInput(
        interval="1m",
        period=120,
        history_provider=QuestDBLoader("db", fetcher=fetcher),
        event_recorder=QuestDBRecorder("db"),
    )
    assert isinstance(stream.history_provider.fetcher, BinanceFetcher)
    assert stream.history_provider.dsn == "db"
    assert stream.event_recorder.dsn == "db"
