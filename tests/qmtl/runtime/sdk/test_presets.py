"""Tests for QMTL v2.0 policy presets."""

from __future__ import annotations

import pytest

from qmtl.runtime.sdk.presets import (
    PolicyPreset,
    PresetPolicy,
    ThresholdConfig,
    TopKConfig,
    get_preset,
    list_presets,
    PRESETS,
    PRESET_SANDBOX,
    PRESET_CONSERVATIVE,
    PRESET_MODERATE,
    PRESET_AGGRESSIVE,
)


class TestPolicyPreset:
    """Tests for PolicyPreset enum."""

    def test_preset_values(self):
        assert PolicyPreset.SANDBOX == "sandbox"
        assert PolicyPreset.CONSERVATIVE == "conservative"
        assert PolicyPreset.MODERATE == "moderate"
        assert PolicyPreset.AGGRESSIVE == "aggressive"

    def test_preset_from_string(self):
        assert PolicyPreset("sandbox") == PolicyPreset.SANDBOX
        assert PolicyPreset("conservative") == PolicyPreset.CONSERVATIVE

    def test_invalid_preset(self):
        with pytest.raises(ValueError):
            PolicyPreset("invalid")


class TestThresholdConfig:
    """Tests for ThresholdConfig."""

    def test_min_only(self):
        config = ThresholdConfig(metric="sharpe", min=1.0)
        d = config.to_dict()
        assert d["metric"] == "sharpe"
        assert d["min"] == 1.0
        assert "max" not in d

    def test_max_only(self):
        config = ThresholdConfig(metric="max_drawdown", max=0.2)
        d = config.to_dict()
        assert d["max"] == 0.2
        assert "min" not in d

    def test_min_and_max(self):
        config = ThresholdConfig(metric="win_rate", min=0.4, max=0.8)
        d = config.to_dict()
        assert d["min"] == 0.4
        assert d["max"] == 0.8


class TestPresetPolicy:
    """Tests for PresetPolicy."""

    def test_to_policy_dict_empty(self):
        policy = PresetPolicy(name="test", description="Test policy")
        d = policy.to_policy_dict()
        assert d == {}

    def test_to_policy_dict_with_thresholds(self):
        policy = PresetPolicy(
            name="test",
            description="Test policy",
            thresholds=[
                ThresholdConfig(metric="sharpe", min=1.0),
                ThresholdConfig(metric="max_drawdown", max=0.2),
            ],
        )
        d = policy.to_policy_dict()
        assert "thresholds" in d
        assert "sharpe" in d["thresholds"]
        assert "max_drawdown" in d["thresholds"]

    def test_to_policy_dict_with_top_k(self):
        policy = PresetPolicy(
            name="test",
            description="Test policy",
            top_k=TopKConfig(metric="sharpe", k=5),
        )
        d = policy.to_policy_dict()
        assert d["top_k"]["metric"] == "sharpe"
        assert d["top_k"]["k"] == 5

    def test_to_yaml(self):
        policy = PresetPolicy(
            name="test",
            description="Test policy",
            allow_live=True,
            max_strategies=5,
            thresholds=[ThresholdConfig(metric="sharpe", min=1.0)],
        )
        yaml_str = policy.to_yaml()
        assert "name: test" in yaml_str
        assert "allow_live: true" in yaml_str
        assert "max_strategies: 5" in yaml_str


class TestGetPreset:
    """Tests for get_preset function."""

    def test_get_by_enum(self):
        policy = get_preset(PolicyPreset.CONSERVATIVE)
        assert policy.name == "conservative"
        assert policy.allow_live is True

    def test_get_by_string(self):
        policy = get_preset("moderate")
        assert policy.name == "moderate"

    def test_get_by_string_case_insensitive(self):
        policy = get_preset("AGGRESSIVE")
        assert policy.name == "aggressive"

    def test_invalid_preset_name(self):
        with pytest.raises(ValueError) as exc_info:
            get_preset("invalid")
        assert "Unknown preset" in str(exc_info.value)


class TestListPresets:
    """Tests for list_presets function."""

    def test_list_presets_count(self):
        presets = list_presets()
        assert len(presets) == 4

    def test_list_presets_content(self):
        presets = list_presets()
        names = [p["name"] for p in presets]
        assert "sandbox" in names
        assert "conservative" in names
        assert "moderate" in names
        assert "aggressive" in names

    def test_list_presets_fields(self):
        presets = list_presets()
        for p in presets:
            assert "name" in p
            assert "description" in p
            assert "allow_live" in p
            assert "max_strategies" in p


class TestPresetDefinitions:
    """Tests for preset definitions."""

    def test_sandbox_no_live(self):
        assert PRESET_SANDBOX.allow_live is False

    def test_conservative_strict_thresholds(self):
        assert PRESET_CONSERVATIVE.allow_live is True
        assert len(PRESET_CONSERVATIVE.thresholds) >= 3
        sharpe_threshold = next(
            (t for t in PRESET_CONSERVATIVE.thresholds if t.metric == "sharpe"),
            None,
        )
        assert sharpe_threshold is not None
        assert sharpe_threshold.min is not None
        assert sharpe_threshold.min >= 1.0

    def test_moderate_balanced(self):
        assert PRESET_MODERATE.max_strategies > PRESET_CONSERVATIVE.max_strategies
        sharpe_threshold = next(
            (t for t in PRESET_MODERATE.thresholds if t.metric == "sharpe"),
            None,
        )
        conservative_sharpe = next(
            (t for t in PRESET_CONSERVATIVE.thresholds if t.metric == "sharpe"),
            None,
        )
        assert sharpe_threshold is not None
        assert sharpe_threshold.min is not None
        assert conservative_sharpe is not None
        assert conservative_sharpe.min is not None
        assert sharpe_threshold.min < conservative_sharpe.min

    def test_aggressive_high_risk(self):
        assert PRESET_AGGRESSIVE.max_strategies > PRESET_MODERATE.max_strategies
        assert PRESET_AGGRESSIVE.correlation is not None
        assert PRESET_MODERATE.correlation is not None
        assert PRESET_AGGRESSIVE.correlation.max > PRESET_MODERATE.correlation.max

    def test_all_presets_in_registry(self):
        assert len(PRESETS) == 4
        for preset_enum in PolicyPreset:
            assert preset_enum in PRESETS
