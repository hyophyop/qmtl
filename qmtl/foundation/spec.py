from __future__ import annotations

"""Architecture spec version map used for design-drift checks.

Each key corresponds to a document under
``docs/<default_locale>/architecture/<key>.md`` (default locale is ``ko``) and
the value is the expected ``spec_version`` declared in that document's YAML
front-matter.
"""

ARCH_SPEC_VERSIONS: dict[str, str] = {
    # Keep in sync with docs/ko/architecture/architecture.md front-matter
    "architecture": "v1.0",
    # Keep in sync with docs/ko/architecture/gateway.md front-matter
    "gateway": "v1.2",
    # Keep in sync with docs/ko/architecture/dag-manager.md front-matter
    "dag-manager": "v1.1",
    # Keep in sync with docs/ko/architecture/worldservice.md front-matter
    "worldservice": "v1.0",
    # Keep in sync with docs/ko/architecture/controlbus.md front-matter
    "controlbus": "v1.0",
}

__all__ = ["ARCH_SPEC_VERSIONS"]
