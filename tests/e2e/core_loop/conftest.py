from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest
import yaml

from .stack import CoreLoopStackHandle, bootstrap_core_loop_stack


@pytest.fixture(scope="session")
def core_loop_artifact_dir():
    path = Path(os.environ.get("CORE_LOOP_ARTIFACT_DIR", ".artifacts/core_loop"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def core_loop_worlds_dir() -> Path:
    return Path(__file__).parent / "worlds"


@pytest.fixture(scope="session")
def core_loop_stack(core_loop_worlds_dir: Path) -> Iterator[CoreLoopStackHandle]:
    handle = bootstrap_core_loop_stack(core_loop_worlds_dir)
    try:
        yield handle
    finally:
        if handle.close:
            handle.close()


@pytest.fixture(scope="session")
def core_loop_world_id(core_loop_stack: CoreLoopStackHandle, core_loop_worlds_dir: Path) -> str:
    if core_loop_stack.world_ids:
        return core_loop_stack.world_ids[0]

    env_world = os.environ.get("CORE_LOOP_WORLD_ID")
    if env_world:
        return env_world

    if core_loop_stack.mode == "service":
        pytest.skip("Set CORE_LOOP_WORLD_ID(S) to point at a provisioned world for service-mode runs")

    sample_world = next(core_loop_worlds_dir.glob("*.yml"), None)
    if sample_world:
        try:
            data = yaml.safe_load(sample_world.read_text())
            wid = data.get("world", {}).get("id")
            if wid:
                return str(wid)
        except Exception:
            pass
        return sample_world.stem.replace("_", "-")

    pytest.skip("No world id available for core loop tests; set CORE_LOOP_WORLD_ID")
