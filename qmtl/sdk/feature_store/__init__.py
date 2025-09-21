"""Feature Artifact Plane utilities for the SDK.

This package provides the primitives required to persist immutable feature
artifacts that can be safely reused across execution domains.  The default
implementation stores artifacts on the local filesystem, but the store is
pluggable so alternative backends (object storage, RocksDB) can be injected
without changing strategy code.
"""

from .types import (
    FeatureArtifact,
    FeatureArtifactKey,
    FeatureDescriptor,
    FeatureStoreConfig,
    FeatureStoreContext,
)
from .store import FeatureArtifactStore

__all__ = [
    "FeatureArtifact",
    "FeatureArtifactKey",
    "FeatureArtifactStore",
    "FeatureDescriptor",
    "FeatureStoreConfig",
    "FeatureStoreContext",
]

