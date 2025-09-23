from qmtl.runtime.transforms.fill_dlq import validate_fill_or_dlq


def test_fill_dlq_valid():
    ok = {"symbol": "AAPL", "quantity": 1.0, "fill_price": 10.0}
    assert validate_fill_or_dlq(ok) == ok


def test_fill_dlq_invalid_routes_to_dlq():
    bad = {"symbol": 123, "quantity": "x"}
    out = validate_fill_or_dlq(bad)
    assert out.get("dlq") is True and out.get("payload") == bad

