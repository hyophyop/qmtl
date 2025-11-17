"""Preset system for common layer combinations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .metadata import Layer


@dataclass
class PresetConfig:
    """Configuration for a project preset."""

    name: str
    description: str
    layers: List[Layer]
    template_choices: Dict[Layer, str] = field(default_factory=dict)
    config: Dict[str, bool | str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict) -> PresetConfig:
        """Load preset from dictionary."""
        layers = [Layer(layer_name) for layer_name in data.get("layers", [])]
        template_choices = {
            Layer(k): v for k, v in data.get("template_choices", {}).items()
        }
        return cls(
            name=data["name"],
            description=data["description"],
            layers=layers,
            template_choices=template_choices,
            config=data.get("config", {}),
        )


class PresetLoader:
    """Loads and manages project presets."""

    def __init__(self):
        """Initialize preset loader with built-in presets."""
        self._presets = self._load_builtin_presets()

    def _load_builtin_presets(self) -> Dict[str, PresetConfig]:
        """Load built-in presets."""
        return {
            "minimal": PresetConfig(
                name="minimal",
                description="Minimal strategy for backtesting and research",
                layers=[Layer.DATA, Layer.SIGNAL],
                template_choices={
                    Layer.DATA: "stream_input",
                    Layer.SIGNAL: "single_indicator",
                },
                config={
                    "include_sample_data": True,
                    "include_notebooks": True,
                },
            ),
            "production": PresetConfig(
                name="production",
                description="Production-ready trading strategy with full execution pipeline",
                layers=[
                    Layer.DATA,
                    Layer.SIGNAL,
                    Layer.EXECUTION,
                    Layer.BROKERAGE,
                    Layer.MONITORING,
                ],
                template_choices={
                    Layer.DATA: "ccxt_provider",
                    Layer.SIGNAL: "multi_indicator",
                    Layer.EXECUTION: "nodeset",
                    Layer.BROKERAGE: "ccxt_binance",
                    Layer.MONITORING: "metrics",
                },
                config={
                    "include_backend_templates": True,
                    "include_docker_compose": True,
                },
            ),
            "research": PresetConfig(
                name="research",
                description="Research-focused strategy with analysis tools",
                layers=[Layer.DATA, Layer.SIGNAL, Layer.MONITORING],
                template_choices={
                    Layer.DATA: "stream_input",
                    Layer.SIGNAL: "multi_indicator",
                    Layer.MONITORING: "metrics",
                },
                config={
                    "include_notebooks": True,
                    "include_sample_data": True,
                    "include_docs": True,
                },
            ),
            "execution": PresetConfig(
                name="execution",
                description="Execution layer for external signals",
                layers=[Layer.EXECUTION, Layer.BROKERAGE],
                template_choices={
                    Layer.EXECUTION: "nodeset",
                    Layer.BROKERAGE: "ccxt_binance",
                },
                config={
                    "signal_source": "external",
                },
            ),
        }

    def get_preset(self, name: str) -> Optional[PresetConfig]:
        """Get a preset by name.

        Args:
            name: Preset name

        Returns:
            PresetConfig if found, None otherwise
        """
        return self._presets.get(name)

    def list_presets(self) -> List[str]:
        """List all available preset names.

        Returns:
            List of preset names
        """
        return sorted(self._presets.keys())

    def get_preset_info(self, name: str) -> Optional[Dict]:
        """Get detailed information about a preset.

        Args:
            name: Preset name

        Returns:
            Dictionary with preset details, None if not found
        """
        preset = self.get_preset(name)
        if not preset:
            return None

        return {
            "name": preset.name,
            "description": preset.description,
            "layers": [layer.value for layer in preset.layers],
            "template_choices": {
                layer.value: template
                for layer, template in preset.template_choices.items()
            },
            "config": preset.config,
        }

    def load_preset_from_file(self, path: Path) -> PresetConfig:
        """Load a preset from a YAML file.

        Args:
            path: Path to preset YAML file

        Returns:
            PresetConfig loaded from file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is invalid
        """
        # TODO: Implement YAML loading
        # For now, raise NotImplementedError
        raise NotImplementedError("Custom preset loading not yet implemented")

    def register_preset(self, preset: PresetConfig) -> None:
        """Register a custom preset.

        Args:
            preset: PresetConfig to register
        """
        self._presets[preset.name] = preset
