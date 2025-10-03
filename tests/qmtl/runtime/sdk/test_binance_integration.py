from qmtl.runtime.sdk import StreamInput, EventRecorderService
from qmtl.runtime.io import QuestDBHistoryProvider, QuestDBRecorder, BinanceFetcher
from qmtl.runtime.io import binance_fetcher as bf_mod


def test_binance_stream_components(monkeypatch) -> None:
    bf_mod._close_client_sync()
    monkeypatch.setattr(bf_mod, "_CLIENT", None)
    fetcher = BinanceFetcher()
    stream = StreamInput(
        interval="1m",
        period=120,
        history_provider=QuestDBHistoryProvider("db", fetcher=fetcher),
        event_service=EventRecorderService(QuestDBRecorder("db")),
    )
    assert isinstance(stream.history_provider.fetcher, BinanceFetcher)
    assert stream.history_provider.dsn == "db"
    assert stream.event_recorder.dsn == "db"
    bf_mod._close_client_sync()
