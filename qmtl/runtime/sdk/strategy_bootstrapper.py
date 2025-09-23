from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from qmtl.foundation.common.compute_key import ComputeContext
from qmtl.services.dagmanager.topic import build_namespace, topic_namespace_enabled
from qmtl.services.gateway.models import StrategyAck

from .feature_store import FeatureArtifactPlane
from .gateway_client import GatewayClient
from .strategy import Strategy
from .tag_manager_service import TagManagerService
from . import metrics as sdk_metrics

logger = logging.getLogger(__name__)


@dataclass
class BootstrapResult:
    manager: Any
    offline_mode: bool
    completed: bool
    dataset_fingerprint: str | None
    tag_service: TagManagerService
    dag_meta: dict | None
    strategy_id: str | None


class StrategyBootstrapper:
    """Prepare strategies for execution by wiring context and Gateway state."""

    def __init__(self, gateway_client: GatewayClient | None = None) -> None:
        self._gateway_client = gateway_client or GatewayClient()

    async def bootstrap(
        self,
        strategy: Strategy,
        *,
        context: ComputeContext,
        world_id: str,
        gateway_url: str | None,
        meta: Mapping[str, Any] | None,
        offline: bool,
        kafka_available: bool,
        trade_mode: str,
        schema_enforcement: str,
        feature_plane: FeatureArtifactPlane | None,
        gateway_context: Mapping[str, str] | None = None,
        skip_gateway_submission: bool = False,
    ) -> BootstrapResult:
        # Apply context and schema enforcement on all nodes
        for node in strategy.nodes:
            setattr(node, "_schema_enforcement", schema_enforcement)
            try:
                node.apply_compute_context(context)
            except AttributeError:
                pass

        tag_service = TagManagerService(gateway_url)
        sdk_metrics.set_world_id(world_id)
        logger.info("[RUN] %s world=%s", strategy.__class__.__name__, world_id)

        dag = strategy.serialize()
        logger.info(
            "Sending DAG to service: %s", [n["node_id"] for n in dag["nodes"]]
        )

        dag_meta = dag.setdefault("meta", {}) if isinstance(dag, dict) else {}
        meta_payload = dict(meta) if isinstance(meta, Mapping) else None

        dataset_fingerprint: str | None = None
        execution_domain_override: str | None = None
        if isinstance(meta_payload, dict):
            raw_domain = meta_payload.get("execution_domain")
            if isinstance(raw_domain, str) and raw_domain.strip():
                execution_domain_override = raw_domain.strip()
            raw_fp = meta_payload.get("dataset_fingerprint") or meta_payload.get(
                "datasetFingerprint"
            )
            if isinstance(raw_fp, str) and raw_fp.strip():
                dataset_fingerprint = raw_fp.strip()

        if topic_namespace_enabled():
            effective_domain = execution_domain_override
            if effective_domain is None:
                if offline:
                    effective_domain = "backtest"
                else:
                    effective_domain = "live" if trade_mode == "live" else "dryrun"
            namespace = build_namespace(world_id, effective_domain)
            if namespace:
                if isinstance(dag_meta, dict):
                    dag_meta["topic_namespace"] = {
                        "world": world_id,
                        "domain": effective_domain,
                    }
                if meta_payload is None:
                    meta_payload = {}
                meta_payload.setdefault("execution_domain", effective_domain)

        meta_for_gateway = meta_payload if meta_payload is not None else meta

        queue_map: dict[str, Any] | Any
        queue_map = {}
        strategy_id: str | None = None
        if gateway_url and not skip_gateway_submission:
            ack = await self._gateway_client.post_strategy(
                gateway_url=gateway_url,
                dag=dag,
                meta=meta_for_gateway,
                context=dict(gateway_context) if gateway_context else None,
                world_id=world_id,
            )
            if isinstance(ack, dict):
                if "error" in ack:
                    raise RuntimeError(ack["error"])
                if isinstance(ack.get("strategy_id"), str):
                    strategy_id = ack["strategy_id"]
                queue_map = ack.get("queue_map", ack)
            elif isinstance(ack, StrategyAck):
                strategy_id = ack.strategy_id
                queue_map = ack.queue_map
            else:
                queue_map = ack

        try:
            manager = tag_service.init(
                strategy, world_id=world_id, strategy_id=strategy_id
            )
        except TypeError:
            manager = tag_service.init(strategy, world_id=world_id)
            if strategy_id is not None and hasattr(manager, "strategy_id"):
                setattr(manager, "strategy_id", strategy_id)

        if strategy_id is not None:
            setattr(strategy, "strategy_id", strategy_id)

        tag_service.apply_queue_map(strategy, queue_map or {})

        if not any(getattr(node, "execute", False) for node in strategy.nodes):
            logger.info("No executable nodes; exiting strategy")
            strategy.on_finish()
            offline_mode = offline or not kafka_available or not gateway_url
            return BootstrapResult(
                manager=manager,
                offline_mode=offline_mode,
                completed=True,
                dataset_fingerprint=dataset_fingerprint,
                tag_service=tag_service,
                dag_meta=dag_meta if isinstance(dag_meta, dict) else None,
                strategy_id=strategy_id,
            )

        offline_mode = offline or not kafka_available or not gateway_url
        await manager.resolve_tags(offline=offline_mode)

        if dataset_fingerprint:
            if isinstance(dag_meta, dict):
                dag_meta.setdefault("dataset_fingerprint", dataset_fingerprint)
            for node in strategy.nodes:
                try:
                    node.dataset_fingerprint = dataset_fingerprint
                except AttributeError:
                    pass

        if feature_plane is not None:
            feature_plane.configure(
                dataset_fingerprint=dataset_fingerprint,
                execution_domain=context.execution_domain,
            )

        return BootstrapResult(
            manager=manager,
            offline_mode=offline_mode,
            completed=False,
            dataset_fingerprint=dataset_fingerprint,
            tag_service=tag_service,
            dag_meta=dag_meta if isinstance(dag_meta, dict) else None,
            strategy_id=strategy_id,
        )


__all__ = ["BootstrapResult", "StrategyBootstrapper"]
