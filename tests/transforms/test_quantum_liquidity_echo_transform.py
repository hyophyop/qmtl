import math

from qmtl.transforms.quantum_liquidity_echo import (
    accumulate_echo,
    amplification_index,
    decide_action,
    quantum_liquidity_echo,
)


def test_accumulate_echo():
    alphas = [1.0, 2.0, 3.0]
    out = accumulate_echo(alphas, delta_t=1.0, tau=2.0)
    expected = sum(
        alpha * math.exp(-k * 1.0 / 2.0)
        for k, alpha in enumerate(alphas, start=1)
    )
    assert math.isclose(out, expected)


def test_amplification_index():
    qe = amplification_index(2.0, sigma=0.5)
    assert qe == 4.0 / 0.5


def test_decide_action():
    assert decide_action(1.0, 10.0, 5.0) == -1
    assert decide_action(-1.0, 10.0, 5.0) == 1
    assert decide_action(1.0, 2.0, 5.0) == 0


def test_quantum_liquidity_echo():
    alphas = [1.0]
    echo, qe, action = quantum_liquidity_echo(alphas, 1.0, 1.0, 0.5, 0.5)
    expected_echo = accumulate_echo(alphas, 1.0, 1.0)
    expected_qe = amplification_index(expected_echo, 0.5)
    expected_action = decide_action(expected_echo, expected_qe, 0.5)
    assert math.isclose(echo, expected_echo)
    assert math.isclose(qe, expected_qe)
    assert action == expected_action
