"""Internal automation helpers (Phase 4+).

This package is intentionally lightweight: it provides library-style building
blocks that can be invoked by CLI wrappers or external processes without
introducing a heavyweight orchestration engine dependency.
"""

from .campaign_executor import CampaignExecutor, CampaignRunConfig, ExecutionResult

__all__ = ["CampaignExecutor", "CampaignRunConfig", "ExecutionResult"]

