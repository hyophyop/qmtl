from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from qmtl.foundation.common.compute_key import ComputeContext
from qmtl.foundation.common.compute_context import resolve_execution_domain
from qmtl.services.dagmanager.topic import build_namespace, topic_namespace_enabled
from qmtl.services.gateway.models import StrategyAck

from .feature_store import FeatureArtifactPlane
from .gateway_client import GatewayClient
from .strategy import Strategy
from .tag_manager_service import TagManagerService
from . import metrics as sdk_metrics

logger = logging.getLogger(__name__)


@dataclass
class GatewaySubmission:
    strategy_id: str | None
    queue_map: dict[str, Any]
    downgraded: bool = False
    downgrade_reason: str | None = None
    safe_mode: bool = False
    context_available: bool = False


@dataclass
class BootstrapResult:
    manager: Any
    offline_mode: bool
    completed: bool
    dataset_fingerprint: str | None
    tag_service: TagManagerService
    dag_meta: dict | None
    strategy_id: str | None
    downgraded: bool = False
    downgrade_reason: str | None = None
    safe_mode: bool = False
    context_available: bool = False


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
        self._apply_context(strategy, context, schema_enforcement)

        tag_service = TagManagerService(gateway_url)
        sdk_metrics.set_world_id(world_id)
        logger.info("[RUN] %s world=%s", strategy.__class__.__name__, world_id)

        dag = strategy.serialize()
        logger.info(
            "Sending DAG to service: %s", [n["node_id"] for n in dag["nodes"]]
        )

        dag_meta = dag.setdefault("meta", {}) if isinstance(dag, dict) else {}
        meta_payload, dataset_fingerprint, execution_domain_override = (
            self._extract_meta_payload(meta)
        )
        dag_meta, meta_payload = self._attach_topic_namespace(
            dag_meta,
            meta_payload,
            world_id=world_id,
            offline=offline,
            trade_mode=trade_mode,
            execution_domain_override=execution_domain_override,
        )
        meta_for_gateway = meta_payload if meta_payload is not None else meta

        submission = await self._maybe_submit_strategy(
            gateway_url=gateway_url,
            skip_gateway_submission=skip_gateway_submission,
            dag=dag,
            meta_for_gateway=meta_for_gateway,
            gateway_context=gateway_context,
            world_id=world_id,
            trade_mode=trade_mode,
        )

        manager = self._init_tag_manager(
            tag_service, strategy, world_id=world_id, strategy_id=submission.strategy_id
        )
        self._propagate_strategy_attrs(
            strategy, strategy_id=submission.strategy_id, gateway_url=gateway_url
        )
        tag_service.apply_queue_map(strategy, submission.queue_map or {})

        offline_mode = self._compute_offline_mode(
            offline=offline, kafka_available=kafka_available, gateway_url=gateway_url
        )

        if self._no_executable_nodes(strategy):
            logger.info("No executable nodes; exiting strategy")
            strategy.on_finish()
            return self._make_result(
                manager=manager,
                offline_mode=offline_mode,
                completed=True,
                dataset_fingerprint=dataset_fingerprint,
                tag_service=tag_service,
                dag_meta=dag_meta,
                strategy_id=submission.strategy_id,
                downgraded=submission.downgraded,
                downgrade_reason=submission.downgrade_reason,
                safe_mode=submission.safe_mode,
                context_available=submission.context_available,
            )

        await manager.resolve_tags(offline=offline_mode)
        self._apply_dataset_fingerprint(
            strategy, dag_meta, dataset_fingerprint=dataset_fingerprint
        )
        self._configure_feature_plane(
            feature_plane,
            dataset_fingerprint=dataset_fingerprint,
            execution_domain=context.execution_domain,
        )

        return self._make_result(
            manager=manager,
            offline_mode=offline_mode,
            completed=False,
            dataset_fingerprint=dataset_fingerprint,
            tag_service=tag_service,
            dag_meta=dag_meta,
            strategy_id=submission.strategy_id,
            downgraded=submission.downgraded,
            downgrade_reason=submission.downgrade_reason,
            safe_mode=submission.safe_mode,
            context_available=submission.context_available,
        )

    def _apply_context(
        self,
        strategy: Strategy,
        context: ComputeContext,
        schema_enforcement: str,
    ) -> None:
        for node in strategy.nodes:
            setattr(node, "_schema_enforcement", schema_enforcement)
            try:
                node.apply_compute_context(context)
            except AttributeError:
                continue

    def _extract_meta_payload(
        self, meta: Mapping[str, Any] | None
    ) -> tuple[dict | None, str | None, str | None]:
        meta_payload = dict(meta) if isinstance(meta, Mapping) else None
        if not isinstance(meta_payload, dict):
            return None, None, None

        dataset_fingerprint: str | None = None
        execution_domain_override: str | None = None
        raw_domain = meta_payload.get("execution_domain")
        if isinstance(raw_domain, str) and raw_domain.strip():
            logger.warning(
                "runner.execution_domain_hint_ignored",
                extra={"execution_domain": raw_domain},
            )
            meta_payload.pop("execution_domain", None)
            execution_domain_override = None
        raw_fp = meta_payload.get("dataset_fingerprint") or meta_payload.get(
            "datasetFingerprint"
        )
        if isinstance(raw_fp, str) and raw_fp.strip():
            dataset_fingerprint = raw_fp.strip()
        return meta_payload, dataset_fingerprint, execution_domain_override

    def _attach_topic_namespace(
        self,
        dag_meta: Any,
        meta_payload: dict | None,
        *,
        world_id: str,
        offline: bool,
        trade_mode: str,
        execution_domain_override: str | None,
    ) -> tuple[Any, dict | None]:
        if not topic_namespace_enabled():
            return dag_meta, meta_payload

        effective_domain = execution_domain_override
        if effective_domain is None:
            if offline:
                effective_domain = "backtest"
            else:
                effective_domain = "live" if trade_mode == "live" else "dryrun"
        effective_domain = resolve_execution_domain(effective_domain) or effective_domain

        if effective_domain:
            meta_payload = meta_payload or {}
            meta_payload["execution_domain"] = effective_domain

        namespace = build_namespace(world_id, effective_domain)
        if namespace and isinstance(dag_meta, dict):
            dag_meta["topic_namespace"] = {
                "world": world_id,
                "domain": effective_domain,
            }
        return dag_meta, meta_payload

    async def _maybe_submit_strategy(
        self,
        *,
        gateway_url: str | None,
        skip_gateway_submission: bool,
        dag: Any,
        meta_for_gateway: Any,
        gateway_context: Mapping[str, str] | None,
        world_id: str,
        trade_mode: str,
    ) -> GatewaySubmission:

        if not gateway_url or skip_gateway_submission:
            return GatewaySubmission(strategy_id=None, queue_map={})

        ack = await self._gateway_client.post_strategy(
            gateway_url=gateway_url,
            dag=dag,
            meta=meta_for_gateway,
            context=dict(gateway_context) if gateway_context else None,
            world_id=world_id,
        )

        if isinstance(ack, dict):
            if "error" in ack:
                error_detail = str(ack.get("error") or "unknown error")
                raise RuntimeError(
                    "Gateway rejected strategy submission: "
                    f"{error_detail} (world_id={world_id}, trade_mode={trade_mode}, "
                    f"gateway_url={gateway_url})"
                )
        if isinstance(ack, StrategyAck):
            return GatewaySubmission(
                strategy_id=ack.strategy_id,
                queue_map=ack.queue_map or {},
                downgraded=bool(ack.downgraded),
                downgrade_reason=ack.downgrade_reason,
                safe_mode=bool(ack.safe_mode),
                context_available=True,
            )
        downgrade_reason = ack.get("downgrade_reason")
        if not isinstance(downgrade_reason, str):
            downgrade_reason = None
        strategy_id = ack.get("strategy_id")
        queue_map_val = ack.get("queue_map", ack)
        queue_map = queue_map_val if isinstance(queue_map_val, dict) else {}
        return GatewaySubmission(
            strategy_id=strategy_id if isinstance(strategy_id, str) else None,
            queue_map=queue_map,
            downgraded=bool(ack.get("downgraded", False)),
            downgrade_reason=downgrade_reason,
            safe_mode=bool(ack.get("safe_mode", False)),
            context_available=True,
        )

    def _init_tag_manager(
        self,
        tag_service: TagManagerService,
        strategy: Strategy,
        *,
        world_id: str,
        strategy_id: str | None,
    ):
        try:
            return tag_service.init(
                strategy, world_id=world_id, strategy_id=strategy_id
            )
        except TypeError:
            manager = tag_service.init(strategy, world_id=world_id)
            if strategy_id is not None and hasattr(manager, "strategy_id"):
                setattr(manager, "strategy_id", strategy_id)
            return manager

    def _propagate_strategy_attrs(
        self,
        strategy: Strategy,
        *,
        strategy_id: str | None,
        gateway_url: str | None,
    ) -> None:
        if strategy_id is not None:
            setattr(strategy, "strategy_id", strategy_id)
            for node in strategy.nodes:
                try:
                    setattr(node, "strategy_id", strategy_id)
                except Exception:
                    continue
        if gateway_url:
            setattr(strategy, "gateway_url", gateway_url)
            for node in strategy.nodes:
                try:
                    setattr(node, "gateway_url", gateway_url)
                except Exception:
                    continue

    @staticmethod
    def _compute_offline_mode(
        *, offline: bool, kafka_available: bool, gateway_url: str | None
    ) -> bool:
        return offline or not kafka_available or not gateway_url

    @staticmethod
    def _no_executable_nodes(strategy: Strategy) -> bool:
        return not any(getattr(node, "execute", False) for node in strategy.nodes)

    def _make_result(
        self,
        *,
        manager: Any,
        offline_mode: bool,
        completed: bool,
        dataset_fingerprint: str | None,
        tag_service: TagManagerService,
        dag_meta: Any,
        strategy_id: str | None,
        downgraded: bool = False,
        downgrade_reason: str | None = None,
        safe_mode: bool = False,
        context_available: bool = False,
    ) -> BootstrapResult:
        dag_meta_dict = dag_meta if isinstance(dag_meta, dict) else None
        return BootstrapResult(
            manager=manager,
            offline_mode=offline_mode,
            completed=completed,
            dataset_fingerprint=dataset_fingerprint,
            tag_service=tag_service,
            dag_meta=dag_meta_dict,
            strategy_id=strategy_id,
            downgraded=downgraded,
            downgrade_reason=downgrade_reason,
            safe_mode=safe_mode,
            context_available=context_available,
        )

    def _apply_dataset_fingerprint(
        self,
        strategy: Strategy,
        dag_meta: Any,
        *,
        dataset_fingerprint: str | None,
    ) -> None:
        if not dataset_fingerprint:
            return
        if isinstance(dag_meta, dict):
            dag_meta.setdefault("dataset_fingerprint", dataset_fingerprint)
        for node in strategy.nodes:
            try:
                node.dataset_fingerprint = dataset_fingerprint
            except AttributeError:
                continue

    @staticmethod
    def _configure_feature_plane(
        feature_plane: FeatureArtifactPlane | None,
        *,
        dataset_fingerprint: str | None,
        execution_domain: str | None,
    ) -> None:
        if feature_plane is None:
            return
        feature_plane.configure(
            dataset_fingerprint=dataset_fingerprint,
            execution_domain=execution_domain,
        )


__all__ = ["BootstrapResult", "StrategyBootstrapper"]
