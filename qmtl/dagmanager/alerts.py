from __future__ import annotations

"""Alerting helpers for PagerDuty and Slack."""

from dataclasses import dataclass
from typing import Protocol

import httpx


class PagerDutySender(Protocol):
    """Protocol for sending PagerDuty events."""

    def send(self, message: str) -> None:
        ...


class SlackSender(Protocol):
    """Protocol for sending Slack messages."""

    def send(self, message: str) -> None:
        ...


@dataclass
class PagerDutyClient:
    url: str

    def send(self, message: str) -> None:  # pragma: no cover - simple wrapper
        httpx.post(self.url, json={"text": message})


@dataclass
class SlackClient:
    url: str

    def send(self, message: str) -> None:  # pragma: no cover - simple wrapper
        httpx.post(self.url, json={"text": message})


@dataclass
class AlertManager:
    pagerduty: PagerDutySender
    slack: SlackSender

    def send_pagerduty(self, message: str) -> None:
        self.pagerduty.send(message)

    def send_slack(self, message: str) -> None:
        self.slack.send(message)


__all__ = ["PagerDutyClient", "SlackClient", "AlertManager"]
