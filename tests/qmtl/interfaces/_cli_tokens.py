from __future__ import annotations

from importlib import import_module
from typing import Dict, List

from qmtl.interfaces.cli import PRIMARY_DISPATCH


def resolve_cli_tokens(*module_paths: str) -> List[str]:
    """Return CLI tokens that dispatch to the provided module chain.

    Each ``module_path`` must correspond to the entry point referenced by the
    current dispatch table. The first lookup uses ``PRIMARY_DISPATCH`` and each
    subsequent lookup expects the module to expose ``<NAME>_DISPATCH`` (where
    ``<NAME>`` is the trailing segment of the module path, upper-cased). This
    mirrors the CLI architecture so tests can anchor on module locations rather
    than string literals.
    """

    tokens: List[str] = []
    dispatch: Dict[str, str] = dict(PRIMARY_DISPATCH)

    for index, module_path in enumerate(module_paths):
        try:
            command = next(cmd for cmd, target in dispatch.items() if target == module_path)
        except StopIteration as exc:
            raise ValueError(f"Module '{module_path}' not found in dispatch table at depth {index}") from exc

        tokens.append(command)

        module = import_module(module_path)
        attr = f"{module_path.rsplit('.', 1)[-1].upper()}_DISPATCH"
        dispatch = getattr(module, attr, {})

    return tokens
