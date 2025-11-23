"""Smoke coverage for thin transform shims and placeholders."""

import importlib
import math

import pytest


@pytest.mark.parametrize(
    (
        "module_name",
        "runtime_module",
        "symbol",
        "args",
        "expected",
    ),
    [
        (
            "acceptable_price_band",
            "acceptable_price_band",
            "overshoot",
            (0.2, 1.0, 1.5),
            0.0,
        ),
        (
            "execution_diffusion_contraction",
            "execution_diffusion_contraction",
            "hazard_probability",
            ([0.0, 0.5], [0.0, 1.0, 1.0]),
            1.0 / (1.0 + math.exp(-0.5)),
        ),
        (
            "gap_amplification",
            "gap_amplification",
            "cancel_limit_ratio",
            (2.0, 4.0),
            0.5,
        ),
        (
            "hazard_utils",
            "hazard_utils",
            "execution_cost",
            (0.1, 0.02, 0.03),
            0.1,
        ),
        (
            "impact",
            "impact",
            "impact",
            (100.0, 200.0, 10.0, 0.5),
            math.sqrt(0.5) / (10.0**0.5),
        ),
        (
            "order_book_clustering_collapse",
            "order_book_clustering_collapse",
            "hazard_probability",
            (
                {
                    "C": 0.0,
                    "Cliff": 0.0,
                    "Gap": 0.0,
                    "CH": 0.0,
                    "RL": 0.0,
                    "Shield": 0.0,
                    "QDT_inv": 0.0,
                    "Pers": 0.0,
                },
                (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            ),
            0.5,
        ),
        (
            "publisher",
            "publisher",
            "publisher_node",
            ("payload",),
            "payload",
        ),
        (
            "quantum_liquidity_echo",
            "quantum_liquidity_echo",
            "accumulate_echo",
            ([1.0, 0.5], 1.0, 2.0),
            sum(
                alpha * math.exp(-k * 1.0 / 2.0)
                for k, alpha in enumerate([1.0, 0.5], start=1)
            ),
        ),
        (
            "rate_of_change",
            "rate_of_change",
            "rate_of_change_series",
            ([1.0, 2.0],),
            1.0,
        ),
        (
            "resiliency",
            "resiliency",
            "impact",
            (50.0, 100.0, 10.0, 0.5),
            math.sqrt(0.5) / (10.0**0.5),
        ),
        (
            "tactical_liquidity_bifurcation",
            "tactical_liquidity_bifurcation",
            "tlbh_alpha",
            (0.6, 0.5, 1.2, 0.1, 1.0, 0.0, 0.0),
            0.6 * 0.5 * 1.2,
        ),
    ],
)
def test_transform_shims_passthrough_and_execute(
    module_name: str, runtime_module: str, symbol: str, args: tuple, expected: float | str
) -> None:
    module = importlib.import_module(f"qmtl.transforms.{module_name}")
    runtime = importlib.import_module(f"qmtl.runtime.transforms.{runtime_module}")

    exported = getattr(module, symbol)
    runtime_attr = getattr(runtime, symbol)

    assert exported is runtime_attr

    result = exported(*args)
    if isinstance(expected, float):
        assert result == pytest.approx(expected)
    else:
        assert result == expected


def test_credit_liquidity_amplification_placeholder_returns_zero() -> None:
    from qmtl.transforms.credit_liquidity_amplification import credit_liquidity_amplification

    assert credit_liquidity_amplification(0, 0, 0, 0, 0, 0, 0, 0, 0) == 0.0
