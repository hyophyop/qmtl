from __future__ import annotations

"""Alerting helpers for PagerDuty and Slack."""

from dataclasses import dataclass
from typing import Protocol

import httpx


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

    async def send(self, message: str) -> None:  # pragma: no cover - simple wrapper
        async with httpx.AsyncClient() as client:
            await client.post(self.url, json={"text": message})


@dataclass
class SlackClient:
    url: str

    async def send(self, message: str) -> None:  # pragma: no cover - simple wrapper
        async with httpx.AsyncClient() as client:
            await client.post(self.url, json={"text": message})


@dataclass
class AlertManager:
    pagerduty: PagerDutySender
    slack: SlackSender

    async def send_pagerduty(self, message: str) -> None:
        await self.pagerduty.send(message)

    async def send_slack(self, message: str) -> None:
        await self.slack.send(message)


__all__ = ["PagerDutyClient", "SlackClient", "AlertManager"]
