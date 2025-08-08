"""Protocol buffer generated modules."""

from . import dagmanager_pb2
import sys

sys.modules.setdefault("dagmanager_pb2", dagmanager_pb2)

from . import dagmanager_pb2_grpc
sys.modules.setdefault("dagmanager_pb2_grpc", dagmanager_pb2_grpc)

__all__ = [
    "dagmanager_pb2",
    "dagmanager_pb2_grpc",
]
