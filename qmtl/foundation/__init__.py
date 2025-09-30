"""Foundation layer for shared infrastructure modules."""

from . import common, kafka, proto, schema
from .config import *  # noqa: F401,F403
from .spec import *  # noqa: F401,F403

__all__ = ["common", "kafka", "proto", "schema"]
__all__ += [name for name in globals() if name not in __all__ and not name.startswith("_")]
