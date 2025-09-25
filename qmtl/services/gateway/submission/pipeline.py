from __future__ import annotations

"""High-level orchestration for the strategy submission pipeline."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List

from .context_service import ComputeContextService, StrategyComputeContext
from .dag_loader import DagLoader
from .diff_executor import DiffExecutor
from .node_identity import NodeIdentityValidator
from .queue_map_resolver import QueueMapResolver

if TYPE_CHECKING:  # pragma: no cover - typing hints only
    from qmtl.services.gateway.models import StrategySubmit


@dataclass
class PreparedSubmission:
    dag: dict[str, Any]
    strategy_context: StrategyComputeContext
    node_ids_crc32: int

    @property
    def compute_context(self) -> StrategyComputeContext:
        return self.strategy_context

    @property
    def context_payload(self) -> dict[str, Any]:
        return self.strategy_context.commit_log_payload()

    @property
    def context_mapping(self) -> dict[str, str]:
        return self.strategy_context.redis_mapping()

    @property
    def worlds(self) -> List[str]:
        return self.strategy_context.worlds_list()


class SubmissionPipeline:
    """Compose submission services to prepare DAGs and downstream calls."""

    def __init__(
        self,
        dagmanager,
        *,
        dag_loader: DagLoader | None = None,
        node_validator: NodeIdentityValidator | None = None,
        context_service: ComputeContextService | None = None,
        diff_executor: DiffExecutor | None = None,
        queue_map_resolver: QueueMapResolver | None = None,
    ) -> None:
        self._dag_loader = dag_loader or DagLoader()
        self._node_validator = node_validator or NodeIdentityValidator()
        self._context_service = context_service or ComputeContextService()
        self._diff_executor = diff_executor or DiffExecutor(dagmanager)
        self._queue_map_resolver = queue_map_resolver or QueueMapResolver(dagmanager)

    async def prepare(self, payload: "StrategySubmit") -> PreparedSubmission:
        loaded = self._dag_loader.load(payload.dag_json)
        dag = loaded.dag
        report = self._node_validator.validate(dag, payload.node_ids_crc32)
        strategy_context = await self._context_service.build(payload)
        return PreparedSubmission(
            dag=dag,
            strategy_context=strategy_context,
            node_ids_crc32=report.computed_checksum,
        )

    async def run_diff(
        self,
        *,
        strategy_id: str,
        dag_json: str,
        worlds: list[str],
        fallback_world_id: str | None,
        compute_ctx: StrategyComputeContext,
        timeout: float,
        prefer_queue_map: bool,
        expected_crc32: int | None = None,
    ) -> tuple[str | None, dict[str, list[dict[str, Any]]] | None]:
        return await self._diff_executor.run(
            strategy_id=strategy_id,
            dag_json=dag_json,
            worlds=worlds,
            fallback_world_id=fallback_world_id,
            compute_ctx=compute_ctx,
            timeout=timeout,
            prefer_queue_map=prefer_queue_map,
            expected_crc32=expected_crc32,
        )

    async def build_queue_map(
        self,
        dag: dict[str, Any],
        worlds: list[str],
        default_world: str | None,
        execution_domain: str | None,
    ) -> dict[str, list[dict[str, Any] | Any]]:
        return await self._queue_map_resolver.build(
            dag,
            worlds,
            default_world,
            execution_domain,
        )
