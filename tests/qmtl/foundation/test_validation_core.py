from __future__ import annotations

from qmtl.foundation.validation_core import (
    Rule,
    RuleSet,
    ValidationMessage,
    ValidationResult,
)


class _AlwaysOkRule:
    code = "OK_RULE"
    description = "Always passes without errors."

    def validate(self, context: object) -> ValidationResult:
        return ValidationResult.success()


class _FailingRule:
    code = "FAIL_RULE"
    description = "Always emits a single error."

    def validate(self, context: object) -> ValidationResult:
        message = ValidationMessage(
            code=self.code,
            message=f"invalid context: {context!r}",
            severity="error",
            field="value",
        )
        return ValidationResult.from_messages(message)


def test_validation_message_to_dict() -> None:
    message = ValidationMessage(
        code="E_TEST",
        message="failed",
        severity="warning",
        hint="fix it",
        field="field_name",
        payload={"extra": "data"},
    )

    as_dict = message.as_dict()
    assert as_dict["code"] == "E_TEST"
    assert as_dict["message"] == "failed"
    assert as_dict["severity"] == "warning"
    assert as_dict["hint"] == "fix it"
    assert as_dict["field"] == "field_name"
    assert as_dict["payload"] == {"extra": "data"}


def test_validation_result_success_and_merge() -> None:
    ok = ValidationResult.success()
    assert ok.ok
    assert tuple(ok.iter_errors()) == ()

    message = ValidationMessage(code="E", message="err")
    failing = ValidationResult.from_messages(message)
    merged = ok.merge(failing)

    assert not merged.ok
    errors = list(merged.iter_errors())
    assert len(errors) == 1
    assert errors[0].code == "E"


def test_rule_set_combines_results() -> None:
    rules: tuple[Rule[object], ...] = (_AlwaysOkRule(), _FailingRule())
    rule_set = RuleSet(rules=rules)

    result = rule_set.validate(context={"value": 1})

    assert not result.ok
    errors = list(result.iter_errors())
    assert len(errors) == 1
    assert errors[0].code == "FAIL_RULE"

