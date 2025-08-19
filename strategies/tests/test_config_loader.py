from strategies.config import load_config


def test_load_config_parses_sections():
    cfg = load_config()
    assert cfg["performance_metrics"]["risk_free_rate"] == 0.01
    assert cfg["signal_thresholds"]["long"] == 0.5
    assert cfg["signal_thresholds"]["short"] == -0.5
    assert cfg["risk_limits"]["size"] == 1.0
    assert cfg["risk_limits"]["stop_loss"] == 0.1
    assert cfg["risk_limits"]["take_profit"] == 0.3
