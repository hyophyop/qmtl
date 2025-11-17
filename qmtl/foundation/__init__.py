"""Foundation layer for shared infrastructure modules."""

from . import adapters, common, kafka, proto, schema
from .validation_core import Rule, RuleSet, ValidationMessage, ValidationResult

__all__ = [
    "adapters",
    "common",
    "kafka",
    "proto",
    "schema",
    "Rule",
    "RuleSet",
    "ValidationMessage",
    "ValidationResult",
]
