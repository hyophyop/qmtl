import pytest

from qmtl.dagmanager.topic import topic_namespace_enabled


@pytest.mark.parametrize("value", [None, "1", "true", "yes", "ON", "unexpected"])
def test_namespace_enabled_by_default(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("QMTL_ENABLE_TOPIC_NAMESPACE", raising=False)
    else:
        monkeypatch.setenv("QMTL_ENABLE_TOPIC_NAMESPACE", value)
    assert topic_namespace_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "disable", "disabled", " False "])
def test_namespace_opt_out(monkeypatch, value):
    monkeypatch.setenv("QMTL_ENABLE_TOPIC_NAMESPACE", value)
    assert topic_namespace_enabled() is False
