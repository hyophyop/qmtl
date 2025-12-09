from __future__ import annotations

from pathlib import Path

from qmtl.model_cards import ModelCardRegistry


def test_model_card_registry_prefers_env_dir(tmp_path, monkeypatch):
    base = tmp_path / "model_cards"
    base.mkdir()
    card_path = base / "strategy-a.yml"
    card_path.write_text(
        "\n".join(
            [
                "strategy_id: strategy-a",
                "model_card_version: v2.0",
                "objective: Demo card",
                "data_overview: placeholder",
                "key_assumptions: [a1]",
                "key_limitations: [l1]",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QMTL_MODEL_CARD_DIR", str(base))

    registry = ModelCardRegistry()
    card = registry.load("strategy-a")

    assert card is not None
    assert card.model_card_version == "v2.0"
    assert registry.version("strategy-a") == "v2.0"
