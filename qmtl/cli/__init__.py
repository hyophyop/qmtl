from __future__ import annotations

ALIAS = __name__

from .._compat import deprecated_module, mirror_module_globals

_target = deprecated_module(ALIAS, "qmtl.interfaces.cli")
mirror_module_globals(_target, globals(), alias=ALIAS)
