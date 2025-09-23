from __future__ import annotations

import inspect

from qmtl.worldservice.storage import audit, edge_overrides, normalization, repositories


def test_repositories_module_re_exports_expected_symbols() -> None:
    assert repositories.AuditLogRepository is audit.AuditLogRepository
    assert repositories.EdgeOverrideRepository is edge_overrides.EdgeOverrideRepository
    assert repositories._REASON_UNSET is edge_overrides._REASON_UNSET
    assert (
        repositories._normalize_execution_domain
        is normalization._normalize_execution_domain
    )
    assert (
        repositories._normalize_world_node_status
        is normalization._normalize_world_node_status
    )
    assert inspect.isclass(repositories.AuditableRepository)
    assert inspect.isclass(repositories.AuditSink)
