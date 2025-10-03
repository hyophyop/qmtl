from __future__ import annotations

import re
from pathlib import Path


def test_no_pytest_plugins_in_nested_conftest() -> None:
    """
    Ensure `pytest_plugins` is defined only in the repository top-level conftest.

    Pytest 8 disallows defining `pytest_plugins` in non-top-level conftests.
    This test guards against regressions by scanning all conftest.py files.
    """
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            repo_root = parent
            break
    else:
        raise RuntimeError("Could not locate repository root from test path")
    assert (repo_root / "pytest.ini").exists(), "repo root discovery failed"

    confs = [p for p in repo_root.rglob("conftest.py")]
    assert confs, "no conftest.py files found"

    # Only the repository root conftest may declare pytest_plugins.
    # Compute the path to the top-level conftest.
    top_level = repo_root / "conftest.py"
    pattern = re.compile(r"^\s*pytest_plugins\s*=", re.MULTILINE)

    offenders: list[str] = []
    for path in confs:
        if path.resolve() == top_level.resolve():
            # Root conftest is allowed to define pytest_plugins.
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            offenders.append(str(path.relative_to(repo_root)))

    assert not offenders, (
        "Defining pytest_plugins in non-top-level conftest is not supported. "
        f"Move declarations to the repo root conftest.py. Offenders: {offenders}"
    )
