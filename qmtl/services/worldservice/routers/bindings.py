from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Response

from ..schemas import (
    BindingsResponse,
    DecisionEnvelope,
    DecisionsRequest,
    SeamlessArtifactPayload,
)
from ..services import WorldService
from qmtl.foundation.common.compute_context import canonicalize_world_mode


def create_bindings_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.post('/worlds/{world_id}/bindings', response_model=BindingsResponse)
    async def post_bindings(world_id: str, payload: DecisionsRequest) -> BindingsResponse:
        store = service.store
        await store.add_bindings(world_id, payload.strategies)
        strategies = await store.list_bindings(world_id)
        return BindingsResponse(strategies=strategies)

    @router.get('/worlds/{world_id}/bindings', response_model=BindingsResponse)
    async def get_bindings(world_id: str) -> BindingsResponse:
        store = service.store
        strategies = await store.list_bindings(world_id)
        return BindingsResponse(strategies=strategies)

    @router.get('/worlds/{world_id}/decide', response_model=DecisionEnvelope)
    async def get_decide(world_id: str, response: Response) -> DecisionEnvelope:
        store = service.store
        version = await store.default_policy_version(world_id)
        now = datetime.now(timezone.utc)
        strategies = await store.get_decisions(world_id)
        candidate_mode = 'active' if strategies else 'validate'
        effective_mode = canonicalize_world_mode(candidate_mode)
        reason = 'policy_evaluated' if strategies else 'no_active_strategies'
        ttl = '300s'
        metadata = await store.latest_history_metadata(world_id)
        dataset_fp = metadata.get('dataset_fingerprint') if metadata else None
        coverage_bounds: List[int] | None = None
        conformance_flags: Dict[str, int] | None = None
        conformance_warnings: List[str] | None = None
        updated_at = metadata.get('updated_at') if metadata else None
        rows = metadata.get('rows') if metadata else None
        if rows is not None and not isinstance(rows, int):
            try:
                rows = int(rows)
            except Exception:
                rows = None
        artifact_payload: SeamlessArtifactPayload | None = None
        as_of_value = metadata.get('as_of') if metadata else None
        if metadata:
            raw_cov = metadata.get('coverage_bounds')
            if isinstance(raw_cov, (list, tuple)):
                coverage_bounds = [int(v) for v in raw_cov]
            raw_flags = metadata.get('conformance_flags')
            if isinstance(raw_flags, dict):
                conformance_flags = dict(raw_flags)
            raw_warnings = metadata.get('conformance_warnings')
            if raw_warnings is not None:
                conformance_warnings = [str(v) for v in raw_warnings]
            candidate_artifact = metadata.get('artifact')
            if isinstance(candidate_artifact, dict):
                artifact_payload = SeamlessArtifactPayload.model_validate(candidate_artifact)
                artifact_as_of = artifact_payload.as_of
                if artifact_as_of and not as_of_value:
                    as_of_value = str(artifact_as_of)
                if rows is None and artifact_payload.rows is not None:
                    try:
                        rows = int(artifact_payload.rows)
                    except Exception:
                        rows = rows
        if as_of_value is None:
            as_of_value = (
                now.replace(microsecond=0)
                .isoformat()
                .replace('+00:00', 'Z')
            )
        etag_parts = [f"w:{world_id}", f"v{version}"]
        if dataset_fp:
            etag_parts.append(str(dataset_fp))
        if as_of_value:
            etag_parts.append(as_of_value)
        if updated_at:
            etag_parts.append(str(updated_at))
        etag_parts.append(str(int(now.timestamp())))
        etag = ':'.join(etag_parts)
        response.headers['Cache-Control'] = 'max-age=300'
        return DecisionEnvelope(
            world_id=world_id,
            policy_version=version,
            effective_mode=effective_mode,
            reason=reason,
            as_of=as_of_value,
            ttl=ttl,
            etag=etag,
            dataset_fingerprint=str(dataset_fp) if dataset_fp else None,
            coverage_bounds=coverage_bounds,
            conformance_flags=conformance_flags,
            conformance_warnings=conformance_warnings,
            history_updated_at=updated_at,
            rows=rows,
            artifact=artifact_payload,
        )

    @router.post('/worlds/{world_id}/decisions', response_model=BindingsResponse)
    async def post_decisions(world_id: str, payload: DecisionsRequest) -> BindingsResponse:
        store = service.store
        await store.set_decisions(world_id, payload.strategies)
        strategies = await store.get_decisions(world_id)
        return BindingsResponse(strategies=strategies)

    return router
