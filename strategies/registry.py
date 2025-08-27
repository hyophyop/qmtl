"""Strategy registry for dynamic loading of strategies."""
from typing import Dict, Type, Any
import importlib
import inspect
from pathlib import Path

try:
    from qmtl.sdk import Strategy
except ImportError:
    # Fallback for type checking
    Strategy = object  # type: ignore


class StrategyRegistry:
    """Registry for managing strategy classes."""

    def __init__(self):
        self._strategies: Dict[str, Type[Any]] = {}
        self._auto_discover_strategies()

    def _auto_discover_strategies(self) -> None:
        """Automatically discover strategy classes in the strategies package."""
        strategies_dir = Path(__file__).parent

        # Discover strategy classes in the main strategies directory
        for py_file in strategies_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue

            module_name = f"strategies.{py_file.stem}"
            try:
                module = importlib.import_module(module_name)
                self._register_strategies_from_module(module, py_file.stem)
            except ImportError:
                continue

        # Discover strategy classes in subdirectories
        for sub_dir in strategies_dir.iterdir():
            if sub_dir.is_dir() and not sub_dir.name.startswith("__"):
                for py_file in sub_dir.glob("*.py"):
                    if py_file.name.startswith("__"):
                        continue

                    module_name = f"strategies.{sub_dir.name}.{py_file.stem}"
                    try:
                        module = importlib.import_module(module_name)
                        self._register_strategies_from_module(module, f"{sub_dir.name}_{py_file.stem}")
                    except ImportError:
                        continue

    def _register_strategies_from_module(self, module: Any, module_key: str) -> None:
        """Register strategy classes from a module."""
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and
                hasattr(obj, 'setup') and callable(getattr(obj, 'setup', None)) and
                name != 'Strategy'):
                # Use module_key + class name as unique identifier
                strategy_key = f"{module_key}_{name}".lower()
                self._strategies[strategy_key] = obj

    def get_strategy(self, name: str) -> Type[Any]:
        """Get a strategy class by name."""
        return self._strategies[name.lower()]

    def list_strategies(self) -> Dict[str, Type[Any]]:
        """List all available strategies."""
        return self._strategies.copy()

    def has_strategy(self, name: str) -> bool:
        """Check if a strategy exists."""
        return name.lower() in self._strategies


# Global registry instance
registry = StrategyRegistry()
