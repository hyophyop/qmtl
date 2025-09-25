"""Custom exception types for better error handling in QMTL SDK."""

__all__ = [
    "QMTLValidationError",
    "NodeValidationError",
    "InvalidParameterError",
    "InvalidTagError",
    "InvalidIntervalError",
    "InvalidPeriodError",
    "InvalidNameError",
    "InvalidSchemaError",
    "SeamlessSLAExceeded",
]


class QMTLValidationError(ValueError):
    """Base class for all QMTL validation errors."""
    pass


class NodeValidationError(QMTLValidationError):
    """Raised when node validation fails."""
    pass


class InvalidParameterError(NodeValidationError):
    """Raised when a parameter value is invalid."""
    pass


class InvalidTagError(NodeValidationError):
    """Raised when a tag format or value is invalid."""
    pass


class InvalidIntervalError(NodeValidationError):
    """Raised when interval validation fails."""
    pass


class InvalidPeriodError(NodeValidationError):
    """Raised when period validation fails."""
    pass


class InvalidNameError(NodeValidationError):
    """Raised when name validation fails."""
    pass


class InvalidSchemaError(NodeValidationError):
    """Raised when dataframe schema validation fails."""
    pass


class SeamlessSLAExceeded(RuntimeError):
    """Raised when a Seamless data request exceeds its configured SLA budget."""

    def __init__(self, phase: str, *, node_id: str, elapsed_ms: float, budget_ms: int | None) -> None:
        detail = (
            f"SLA phase '{phase}' exceeded for node {node_id}: elapsed={elapsed_ms:.1f}ms"
        )
        if budget_ms is not None:
            detail += f" budget={budget_ms}ms"
        super().__init__(detail)
        self.phase = phase
        self.node_id = node_id
        self.elapsed_ms = elapsed_ms
        self.budget_ms = budget_ms

