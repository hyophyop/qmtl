from __future__ import annotations

"""Alerting helpers for PagerDuty and Slack."""

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from qmtl.foundation.common import AsyncCircuitBreaker


async def _post_json(
    url: str,
    payload: dict,
    breaker: AsyncCircuitBreaker | None = None,
) -> None:
    async with httpx.AsyncClient() as client:
        async def send() -> httpx.Response:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"failed with status {resp.status_code}")
            return resp

        wrapped = breaker(send) if breaker else send
        await wrapped()


class PagerDutySender(Protocol):
    """Protocol for sending PagerDuty events."""

    async def send(
        self, message: str, *, topic: str | None = None, node: str | None = None
    ) -> None:
        ...


class SlackSender(Protocol):
    """Protocol for sending Slack messages."""

    async def send(
        self, message: str, *, topic: str | None = None, node: str | None = None
    ) -> None:
        ...


@dataclass
class PagerDutyClient:
    url: str
    breaker: AsyncCircuitBreaker | None = None

    async def send(
        self, message: str, *, topic: str | None = None, node: str | None = None
    ) -> None:  # pragma: no cover - simple wrapper
        payload = {"text": message}
        if topic is not None:
            payload["topic"] = topic
        if node is not None:
            payload["node"] = node
        await _post_json(self.url, payload, self.breaker)


@dataclass
class SlackClient:
    url: str
    breaker: AsyncCircuitBreaker | None = None

    async def send(
        self, message: str, *, topic: str | None = None, node: str | None = None
    ) -> None:  # pragma: no cover - simple wrapper
        payload = {"text": message}
        if topic is not None:
            payload["topic"] = topic
        if node is not None:
            payload["node"] = node
        await _post_json(self.url, payload, self.breaker)


@dataclass
class AlertManager:
    pagerduty: PagerDutySender
    slack: SlackSender
    pagerduty_breaker: AsyncCircuitBreaker = field(default_factory=AsyncCircuitBreaker)
    slack_breaker: AsyncCircuitBreaker = field(default_factory=AsyncCircuitBreaker)

    async def send_pagerduty(
        self, message: str, *, topic: str | None = None, node: str | None = None
    ) -> None:
        if isinstance(self.pagerduty, PagerDutyClient):
            self.pagerduty.breaker = self.pagerduty_breaker
        await self.pagerduty.send(message, topic=topic, node=node)

    async def send_slack(
        self, message: str, *, topic: str | None = None, node: str | None = None
    ) -> None:
        if isinstance(self.slack, SlackClient):
            self.slack.breaker = self.slack_breaker
        await self.slack.send(message, topic=topic, node=node)


__all__ = ["PagerDutyClient", "SlackClient", "AlertManager"]
