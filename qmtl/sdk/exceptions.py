"""Custom exception types for better error handling in QMTL SDK."""

__all__ = [
    "QMTLValidationError",
    "NodeValidationError", 
    "InvalidParameterError",
    "InvalidTagError",
    "InvalidIntervalError",
    "InvalidPeriodError",
    "InvalidNameError",
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