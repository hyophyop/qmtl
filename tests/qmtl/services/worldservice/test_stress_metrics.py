from qmtl.services.worldservice.stress_metrics import normalize_stress_metrics


def test_normalize_stress_metrics_flattens_structures():
    metrics = {
        "stress": {
            "crash": {"max_drawdown": 0.3, "es_99": 0.2},
            "spike": {"var_99": 0.4},
        }
    }
    flat = normalize_stress_metrics(metrics)

    assert flat["stress.crash.max_drawdown"] == 0.3
    assert flat["stress.crash.es_99"] == 0.2
    assert flat["stress.spike.var_99"] == 0.4


def test_normalize_stress_metrics_preserves_dot_keys():
    metrics = {"stress.crash.max_drawdown": 0.25}
    flat = normalize_stress_metrics(metrics)

    assert flat["stress.crash.max_drawdown"] == 0.25
