import pytest
from qmtl.runtime.sdk.activation_manager import ActivationManager


async def _emit(am: ActivationManager, side: str, **fields) -> None:
    payload = {"event": "activation_updated", "data": {"side": side, **fields}}
    await am._on_message(payload)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_freeze_blocks_orders():
    am = ActivationManager()
    # Before any activation, both sides blocked (stale)
    assert am.is_stale()
    assert not am.allow_side("long")
    assert not am.allow_side("short")

    # Long becomes active
    await _emit(am, "long", active=True, weight=1.0, freeze=False, drain=False)
    assert not am.is_stale()
    assert am.allow_side("long")

    # Freeze overrides active
    await _emit(am, "long", active=True, freeze=True)
    assert not am.allow_side("long")


@pytest.mark.asyncio
async def test_drain_blocks_new_orders():
    am = ActivationManager()

    # Short becomes active
    await _emit(am, "short", active=True, weight=1.0)
    assert am.allow_side("short")

    # Drain blocks new submissions
    await _emit(am, "short", active=True, drain=True)
    assert not am.allow_side("short")


@pytest.mark.asyncio
async def test_freeze_blocks_other_side_immediately():
    am = ActivationManager()

    await _emit(am, "long", active=True, weight=1.0)
    await _emit(am, "short", active=True, weight=1.0)

    await _emit(am, "long", active=True, freeze=True)

    assert not am.allow_side("long")
    assert not am.allow_side("short")
    assert am.weight_for_side("short") == 0.0


@pytest.mark.asyncio
async def test_releasing_modes_restores_weights():
    am = ActivationManager()

    await _emit(am, "long", active=True, weight=1.0)
    await _emit(am, "short", active=True, weight=0.5)

    await _emit(am, "short", active=True, drain=True)
    assert not am.allow_side("long")
    assert am.weight_for_side("long") == 0.0

    await _emit(am, "short", active=True, drain=False)
    assert am.allow_side("long")
    assert am.weight_for_side("long") == 1.0
