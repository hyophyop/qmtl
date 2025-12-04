from __future__ import annotations

import textwrap

import pytest

from qmtl.foundation.config import SeamlessConfig
from qmtl.runtime.sdk.world_data import resolve_world_data_selection


def _write_presets(tmp_path) -> str:
    yaml_text = textwrap.dedent(
        """
        data_presets:
          demo.ohlcv:
            interval_ms: 60000
            stabilization_bars: 10
            provider:
              preset: demo.inmemory.ohlcv
              options:
                bars: 5
          alt.ohlcv:
            provider:
              preset: demo.inmemory.ohlcv
        """
    )
    path = tmp_path / "presets.yml"
    path.write_text(yaml_text)
    return str(path)


def _world_payload() -> dict:
    return {
        "world": {
            "id": "core",
            "data": {
                "presets": [
                    {"id": "default", "preset": "demo.ohlcv", "universe": {"symbols": ["BTC"]}},
                    {"id": "alt", "preset": "alt.ohlcv"},
                ]
            },
        }
    }


def test_resolve_world_data_selection_prefers_first_when_no_override(tmp_path) -> None:
    presets_path = _write_presets(tmp_path)
    config = SeamlessConfig(presets_file=presets_path)

    selection = resolve_world_data_selection(
        world_description=_world_payload(),
        world_id="core",
        data_preset_id=None,
        seamless_config=config,
    )

    assert selection is not None
    assert selection.world_preset_id == "default"
    assert selection.data_preset_key == "demo.ohlcv"
    assert selection.spec.provider_name == "demo.inmemory.ohlcv"
    assert selection.spec.interval_ms == 60000


def test_resolve_world_data_selection_uses_override_id(tmp_path) -> None:
    presets_path = _write_presets(tmp_path)
    config = SeamlessConfig(presets_file=presets_path)

    selection = resolve_world_data_selection(
        world_description=_world_payload(),
        world_id="core",
        data_preset_id="alt",
        seamless_config=config,
    )

    assert selection.world_preset_id == "alt"
    assert selection.data_preset_key == "alt.ohlcv"


def test_resolve_world_data_selection_raises_when_missing_preset(tmp_path) -> None:
    presets_path = _write_presets(tmp_path)
    config = SeamlessConfig(presets_file=presets_path)
    bad_world = {"world": {"id": "core"}, "data": {"presets": []}}

    with pytest.raises(ValueError, match="does not define data.presets"):
        resolve_world_data_selection(
            world_description=bad_world,
            world_id="core",
            data_preset_id=None,
            seamless_config=config,
        )


def test_resolve_world_data_selection_raises_when_override_missing(tmp_path) -> None:
    presets_path = _write_presets(tmp_path)
    config = SeamlessConfig(presets_file=presets_path)

    with pytest.raises(ValueError, match="has no data preset with id 'missing'"):
        resolve_world_data_selection(
            world_description=_world_payload(),
            world_id="core",
            data_preset_id="missing",
            seamless_config=config,
        )
