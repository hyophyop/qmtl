from __future__ import annotations

"""Defaults and naming conventions for ControlBus integrations.

These values are intended to be shared across WorldService producers/consumers
so that retries/DLQ/idempotency behaviors are consistent by default.
"""

DEFAULT_CONTROLBUS_TOPIC = "policy"

# RiskHub snapshot consumer defaults.
DEFAULT_RISK_HUB_CONSUMER_GROUP_ID = "worldservice-risk-hub"
DEFAULT_RISK_HUB_MAX_ATTEMPTS = 3
DEFAULT_RISK_HUB_RETRY_BACKOFF_SEC = 0.5
DEFAULT_RISK_HUB_DEDUPE_TTL_SEC: int | None = None
DEFAULT_RISK_HUB_DLQ_TOPIC: str | None = None

# Validation pipeline consumer defaults (EvaluationRun events).
DEFAULT_VALIDATION_CONSUMER_GROUP_ID = "worldservice-validation"
DEFAULT_VALIDATION_MAX_ATTEMPTS = 3
DEFAULT_VALIDATION_RETRY_BACKOFF_SEC = 0.5
DEFAULT_VALIDATION_DEDUPE_TTL_SEC: int | None = None
DEFAULT_VALIDATION_EVENT_TTL_SEC: int | None = None
DEFAULT_VALIDATION_DLQ_TOPIC: str | None = None


def default_dlq_topic(topic: str) -> str:
    return f"{topic}.dlq"


__all__ = [
    "DEFAULT_CONTROLBUS_TOPIC",
    "DEFAULT_RISK_HUB_CONSUMER_GROUP_ID",
    "DEFAULT_RISK_HUB_MAX_ATTEMPTS",
    "DEFAULT_RISK_HUB_RETRY_BACKOFF_SEC",
    "DEFAULT_RISK_HUB_DEDUPE_TTL_SEC",
    "DEFAULT_RISK_HUB_DLQ_TOPIC",
    "DEFAULT_VALIDATION_CONSUMER_GROUP_ID",
    "DEFAULT_VALIDATION_MAX_ATTEMPTS",
    "DEFAULT_VALIDATION_RETRY_BACKOFF_SEC",
    "DEFAULT_VALIDATION_DEDUPE_TTL_SEC",
    "DEFAULT_VALIDATION_EVENT_TTL_SEC",
    "DEFAULT_VALIDATION_DLQ_TOPIC",
    "default_dlq_topic",
]
