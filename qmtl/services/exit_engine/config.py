"""Configuration helpers for the exit engine worker."""

from __future__ import annotations

from dataclasses import dataclass, field


def _env_value(env: dict[str, str], key: str, default: str | None = None) -> str | None:
    value = env.get(key)
    if value is None or str(value).strip() == "":
        return default
    return value


def _required_env(env: dict[str, str], key: str) -> str:
    value = _env_value(env, key)
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class ExitEngineConfig:
    ws_base_url: str
    controlbus_brokers: list[str] = field(default_factory=list)
    controlbus_topic: str = "policy"
    controlbus_group_id: str = "exit-engine"
    freeze_world_ids: set[str] = field(default_factory=set)
    drain_world_ids: set[str] = field(default_factory=set)
    strategy_id: str | None = None
    side: str = "long"
    reason: str = "exit_engine_rule"
    request_timeout_sec: float = 5.0
    auth_header: str = "Authorization"
    auth_token: str | None = None
    ttl_sec_default: int = 900
    ttl_sec_max: int = 86400

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "ExitEngineConfig":
        ws_base_url = _required_env(env, "EXIT_ENGINE_WS_BASE_URL").strip()
        controlbus_brokers = _split_csv(_env_value(env, "CONTROLBUS_BROKERS"))
        controlbus_topic = _env_value(env, "CONTROLBUS_TOPIC", "policy")
        controlbus_group_id = _env_value(env, "CONTROLBUS_GROUP_ID", "exit-engine")
        freeze_world_ids = set(_split_csv(_env_value(env, "EXIT_ENGINE_FREEZE_WORLD_IDS")))
        drain_world_ids = set(_split_csv(_env_value(env, "EXIT_ENGINE_DRAIN_WORLD_IDS")))
        strategy_id = _env_value(env, "EXIT_ENGINE_STRATEGY_ID")
        side = _env_value(env, "EXIT_ENGINE_SIDE", "long")
        reason = _env_value(env, "EXIT_ENGINE_REASON", "exit_engine_rule")
        request_timeout_sec = float(_env_value(env, "EXIT_ENGINE_TIMEOUT_SEC", "5.0"))
        auth_header = _env_value(env, "EXIT_ENGINE_AUTH_HEADER", "Authorization")
        auth_token = _env_value(env, "EXIT_ENGINE_AUTH_TOKEN")
        ttl_sec_default = int(_env_value(env, "EXIT_ENGINE_TTL_SEC_DEFAULT", "900"))
        ttl_sec_max = int(_env_value(env, "EXIT_ENGINE_TTL_SEC_MAX", "86400"))

        return cls(
            ws_base_url=ws_base_url,
            controlbus_brokers=[b for b in controlbus_brokers if b],
            controlbus_topic=str(controlbus_topic),
            controlbus_group_id=str(controlbus_group_id),
            freeze_world_ids=freeze_world_ids,
            drain_world_ids=drain_world_ids,
            strategy_id=str(strategy_id) if strategy_id else None,
            side=str(side),
            reason=str(reason),
            request_timeout_sec=request_timeout_sec,
            auth_header=str(auth_header),
            auth_token=str(auth_token) if auth_token else None,
            ttl_sec_default=ttl_sec_default,
            ttl_sec_max=ttl_sec_max,
        )


def load_exit_engine_config(env: dict[str, str] | None = None) -> ExitEngineConfig:
    data = env if env is not None else {}
    return ExitEngineConfig.from_env(data)


__all__ = ["ExitEngineConfig", "load_exit_engine_config"]
