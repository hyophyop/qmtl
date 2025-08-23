"""Compatibility shim for :mod:`qmtl.common.four_dim_cache`.

The ``FourDimCache`` class lives in :mod:`qmtl.common` and is re-exported here
for backwards compatibility with existing strategy modules.
"""

from qmtl.common import FourDimCache

__all__ = ["FourDimCache"]
