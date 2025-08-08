from __future__ import annotations

"""Alerting helpers for PagerDuty and Slack."""

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from ..common import AsyncCircuitBreaker
from .callbacks import post_with_backoff


class PagerDutySender(Protocol):
    """Protocol for sending PagerDuty events."""

    async def send(self, message: str) -> None:
        ...


class SlackSender(Protocol):
    """Protocol for sending Slack messages."""

    async def send(self, message: str) -> None:
        ...


@dataclass
class PagerDutyClient:
    url: str
    breaker: AsyncCircuitBreaker | None = None

    async def send(self, message: str) -> None:  # pragma: no cover - simple wrapper
        async with httpx.AsyncClient() as client:
            await post_with_backoff(
                self.url,
                {"text": message},
                client=client,
                circuit_breaker=self.breaker,
            )


@dataclass
class SlackClient:
    url: str
    breaker: AsyncCircuitBreaker | None = None

    async def send(self, message: str) -> None:  # pragma: no cover - simple wrapper
        async with httpx.AsyncClient() as client:
            await post_with_backoff(
                self.url,
                {"text": message},
                client=client,
                circuit_breaker=self.breaker,
            )


@dataclass
class AlertManager:
    pagerduty: PagerDutySender
    slack: SlackSender
    pagerduty_breaker: AsyncCircuitBreaker = field(default_factory=AsyncCircuitBreaker)
    slack_breaker: AsyncCircuitBreaker = field(default_factory=AsyncCircuitBreaker)

    async def send_pagerduty(self, message: str) -> None:
        if isinstance(self.pagerduty, PagerDutyClient):
            self.pagerduty.breaker = self.pagerduty_breaker
        await self.pagerduty.send(message)

    async def send_slack(self, message: str) -> None:
        if isinstance(self.slack, SlackClient):
            self.slack.breaker = self.slack_breaker
        await self.slack.send(message)


__all__ = ["PagerDutyClient", "SlackClient", "AlertManager"]
