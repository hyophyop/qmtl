"""Protocol buffer generated modules."""

import importlib
import sys

from . import dagmanager_pb2

sys.modules.setdefault("dagmanager_pb2", dagmanager_pb2)

dagmanager_pb2_grpc = importlib.import_module(f"{__name__}.dagmanager_pb2_grpc")
sys.modules.setdefault("dagmanager_pb2_grpc", dagmanager_pb2_grpc)

__all__ = [
    "dagmanager_pb2",
    "dagmanager_pb2_grpc",
]
