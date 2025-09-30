from __future__ import annotations

"""Architecture spec version map used for design-drift checks.

Each key corresponds to a document under ``docs/architecture/<key>.md`` and the
value is the expected ``spec_version`` declared in that document's YAML
front-matter.
"""

ARCH_SPEC_VERSIONS: dict[str, str] = {
    # Keep in sync with docs/architecture/gateway.md front-matter
    "gateway": "v1.2",
    # Keep in sync with docs/architecture/dag-manager.md front-matter
    "dag-manager": "v1.1",
}

__all__ = ["ARCH_SPEC_VERSIONS"]

