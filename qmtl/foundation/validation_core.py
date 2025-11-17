from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Iterable, Protocol, Sequence, Tuple, TypeVar


@dataclass(frozen=True, slots=True)
class ValidationMessage:
    """Structured description of a single validation outcome."""

    code: str
    message: str
    severity: str = "error"
    hint: str | None = None
    field: str | None = None
    payload: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }
        if self.hint is not None:
            data["hint"] = self.hint
        if self.field is not None:
            data["field"] = self.field
        if self.payload is not None:
            data["payload"] = self.payload
        return data


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Aggregate result produced by one or more validation rules."""

    messages: Tuple[ValidationMessage, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(message.severity == "error" for message in self.messages)

    @classmethod
    def success(cls) -> "ValidationResult":
        return cls(messages=())

    @classmethod
    def from_messages(
        cls, messages: Sequence[ValidationMessage] | ValidationMessage
    ) -> "ValidationResult":
        if isinstance(messages, ValidationMessage):
            return cls(messages=(messages,))
        return cls(messages=tuple(messages))

    def with_message(self, message: ValidationMessage) -> "ValidationResult":
        return ValidationResult(messages=self.messages + (message,))

    def merge(self, *others: "ValidationResult") -> "ValidationResult":
        merged: list[ValidationMessage] = list(self.messages)
        for other in others:
            merged.extend(other.messages)
        return ValidationResult(messages=tuple(merged))

    def iter_errors(self) -> Iterable[ValidationMessage]:
        return (message for message in self.messages if message.severity == "error")

    def iter_warnings(self) -> Iterable[ValidationMessage]:
        return (
            message for message in self.messages if message.severity == "warning"
        )


RuleContextT = TypeVar("RuleContextT", contravariant=True)
ContextT = TypeVar("ContextT")


class Rule(Protocol, Generic[RuleContextT]):
    """Protocol for validation rules used across QMTL."""

    code: str
    description: str

    def validate(self, context: RuleContextT) -> ValidationResult:  # pragma: no cover - interface
        ...


@dataclass(slots=True)
class RuleSet(Generic[ContextT]):
    """Collection of rules executed against a single context."""

    rules: Tuple[Rule[ContextT], ...]

    def validate(self, context: ContextT) -> ValidationResult:
        result = ValidationResult.success()
        for rule in self.rules:
            rule_result = rule.validate(context)
            result = result.merge(rule_result)
        return result


__all__ = ["ValidationMessage", "ValidationResult", "Rule", "RuleSet"]

