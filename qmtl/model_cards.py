"""Lightweight Model Card schema and loader."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _default_card_dirs() -> tuple[Path, ...]:
    env_path = os.environ.get("QMTL_MODEL_CARD_DIR")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path("model_cards"))
    return tuple(candidates)


class ModelCard(BaseModel):
    """Minimal Model Card fields used for evaluation bookkeeping."""

    model_config = ConfigDict(extra="allow")

    strategy_id: str
    model_card_version: str = Field(validation_alias=AliasChoices("model_card_version", "version"))
    objective: str
    data_overview: str | list[str]
    key_assumptions: list[str]
    key_limitations: list[str]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object], *, strategy_id: str | None = None) -> "ModelCard":
        data = dict(payload)
        data.setdefault("strategy_id", strategy_id)
        if not data.get("strategy_id") and strategy_id:
            data["strategy_id"] = strategy_id
        return cls.model_validate(data)


class ModelCardRegistry:
    """Filesystem-backed registry for Model Cards."""

    def __init__(self, *, search_paths: Sequence[str | os.PathLike[str]] | None = None) -> None:
        self._paths: tuple[Path, ...] = tuple(Path(path) for path in (search_paths or _default_card_dirs()))
        self._cache: dict[str, ModelCard | None] = {}

    def _candidate_paths(self, strategy_id: str) -> Iterable[Path]:
        for base in self._paths:
            for ext in ("yaml", "yml"):
                yield base / f"{strategy_id}.{ext}"

    def load(self, strategy_id: str) -> ModelCard | None:
        if strategy_id in self._cache:
            return self._cache[strategy_id]

        for path in self._candidate_paths(strategy_id):
            if not path.is_file():
                continue
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                card = ModelCard.from_mapping(raw, strategy_id=strategy_id)
                self._cache[strategy_id] = card
                return card
            except (OSError, yaml.YAMLError) as exc:  # pragma: no cover - defensive
                logger.warning("Failed to load model card from %s: %s", path, exc)
            except ValidationError as exc:
                logger.warning("Invalid model card payload in %s: %s", path, exc)
                self._cache[strategy_id] = None
                return None

        self._cache[strategy_id] = None
        return None

    def version(self, strategy_id: str) -> str | None:
        card = self.load(strategy_id)
        return card.model_card_version if card else None


__all__ = ["ModelCard", "ModelCardRegistry"]
