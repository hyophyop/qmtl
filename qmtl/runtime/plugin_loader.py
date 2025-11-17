"""Utilities and contracts for loading plugin-style modules safely."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Callable, Mapping, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from qmtl.runtime.sdk.portfolio import Portfolio, Position
    from qmtl.runtime.sdk.strategy import Strategy

StrategyFactory = Callable[[], "Strategy"]


@runtime_checkable
class StrategyModule(Protocol):
    """Module contract for strategy entrypoints."""

    create_strategy: StrategyFactory


@runtime_checkable
class PortfolioModule(Protocol):
    """Module contract for the portfolio helper utilities."""

    Portfolio: type["Portfolio"]
    Position: type["Position"]
    order_value: Callable[[str, float, float], float]


@runtime_checkable
class DagManagerProtocol(Protocol):
    """Minimal interface required by the DAG-based examples."""

    def add_node(
        self,
        name: str,
        func: Callable[..., object],
        inputs: Mapping[str, str] | None = None,
    ) -> None:
        ...

    def execute(self) -> Mapping[str, object]:
        ...


def _load_module_from_path(module_name: str, module_file: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module '{module_name}' from {module_file!s}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_strategy_factory(
    module_path: str, *, fallback: StrategyFactory | None = None
) -> StrategyFactory:
    """Load a strategy factory from ``module_path`` with validation.

    Args:
        module_path: Dotted path to the strategy module.
        fallback: Optional factory returned when the module cannot be imported.

    Returns:
        A callable ``create_strategy`` implementation.

    Raises:
        ImportError: When the module is missing and no ``fallback`` is provided.
        TypeError: When the module does not expose the expected factory.
    """

    try:
        module = importlib.import_module(module_path)
    except ImportError:
        if fallback is None:
            raise
        return fallback

    if not isinstance(module, StrategyModule) or not callable(module.create_strategy):
        raise TypeError(
            f"Module '{module_path}' must define a callable 'create_strategy' entrypoint"
        )

    return module.create_strategy


def load_portfolio_module(
    module_path: str = "qmtl.runtime.sdk.portfolio",
    *,
    module_file: str | Path | None = None,
) -> PortfolioModule:
    """Import the portfolio module and validate its public surface.

    The optional ``module_file`` allows loading the helpers directly from a
    source file in environments where ``qmtl`` is not installed as a package.
    """

    try:
        module = importlib.import_module(module_path)
    except Exception:
        if module_file is None:
            raise
        module = _load_module_from_path(module_path, Path(module_file))

    if not isinstance(module, PortfolioModule):
        raise TypeError(
            f"Module '{module_path}' must expose Portfolio, Position, and order_value"
        )

    return module


def load_dag_manager_class(
    module_path: str = "qmtl.dag_manager",
    *,
    attribute: str = "DAGManager",
    fallback: type[DagManagerProtocol] | None = None,
) -> type[DagManagerProtocol]:
    """Load a DAG manager class matching :class:`DagManagerProtocol`."""

    try:
        module = importlib.import_module(module_path)
        candidate = getattr(module, attribute)
    except (ImportError, AttributeError):
        if fallback is None:
            raise
        candidate = fallback

    if not inspect.isclass(candidate):
        raise TypeError(f"{attribute} from '{module_path}' must be a class")

    if not isinstance(candidate, type) or not all(
        callable(getattr(candidate, name, None)) for name in ("add_node", "execute")
    ):
        raise TypeError(
            f"{attribute} from '{module_path}' must implement add_node and execute"
        )

    return candidate


__all__ = [
    "DagManagerProtocol",
    "PortfolioModule",
    "StrategyFactory",
    "StrategyModule",
    "load_dag_manager_class",
    "load_portfolio_module",
    "load_strategy_factory",
]
