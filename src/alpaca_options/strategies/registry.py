"""Strategy registry for dynamic strategy management."""

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Any, Optional

from alpaca_options.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Registry for managing and loading trading strategies.

    Supports dynamic loading of strategies from Python modules,
    allowing hot-swapping and runtime strategy management.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, type[BaseStrategy]] = {}
        self._instances: dict[str, BaseStrategy] = {}

    def register(self, strategy_class: type[BaseStrategy]) -> None:
        """Register a strategy class.

        Args:
            strategy_class: Strategy class to register.

        Raises:
            ValueError: If strategy name is already registered.
        """
        # Create temporary instance to get name
        temp_instance = strategy_class()
        name = temp_instance.name

        if name in self._strategies:
            raise ValueError(f"Strategy '{name}' is already registered")

        self._strategies[name] = strategy_class
        logger.info(f"Registered strategy: {name}")

    def unregister(self, name: str) -> None:
        """Unregister a strategy by name.

        Args:
            name: Name of the strategy to unregister.
        """
        if name in self._strategies:
            del self._strategies[name]
            if name in self._instances:
                del self._instances[name]
            logger.info(f"Unregistered strategy: {name}")

    def get_strategy_class(self, name: str) -> Optional[type[BaseStrategy]]:
        """Get a registered strategy class by name.

        Args:
            name: Name of the strategy.

        Returns:
            Strategy class if found, None otherwise.
        """
        return self._strategies.get(name)

    async def get_instance(
        self, name: str, config: Optional[dict[str, Any]] = None
    ) -> Optional[BaseStrategy]:
        """Get or create an initialized strategy instance.

        Args:
            name: Name of the strategy.
            config: Configuration for the strategy.

        Returns:
            Initialized strategy instance if found, None otherwise.
        """
        if name in self._instances:
            return self._instances[name]

        strategy_class = self._strategies.get(name)
        if strategy_class is None:
            return None

        instance = strategy_class()
        await instance.initialize(config or {})
        self._instances[name] = instance
        return instance

    def list_strategies(self) -> list[str]:
        """List all registered strategy names.

        Returns:
            List of registered strategy names.
        """
        return list(self._strategies.keys())

    def get_strategy_info(self) -> list[dict[str, str]]:
        """Get information about all registered strategies.

        Returns:
            List of dicts with strategy name and description.
        """
        info = []
        for name, strategy_class in self._strategies.items():
            instance = strategy_class()
            info.append(
                {
                    "name": name,
                    "description": instance.description,
                    "class": strategy_class.__name__,
                }
            )
        return info

    def load_from_module(self, module_path: str) -> int:
        """Load strategies from a Python module.

        Args:
            module_path: Dot-separated module path (e.g., 'alpaca_options.strategies.wheel')

        Returns:
            Number of strategies loaded.
        """
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            logger.error(f"Failed to import module {module_path}: {e}")
            return 0

        return self._load_strategies_from_module(module)

    def load_from_file(self, file_path: Path) -> int:
        """Load strategies from a Python file.

        Args:
            file_path: Path to the Python file.

        Returns:
            Number of strategies loaded.
        """
        if not file_path.exists():
            logger.error(f"Strategy file not found: {file_path}")
            return 0

        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        if spec is None or spec.loader is None:
            logger.error(f"Failed to load spec for {file_path}")
            return 0

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Failed to execute module {file_path}: {e}")
            return 0

        return self._load_strategies_from_module(module)

    def load_from_directory(self, directory: Path) -> int:
        """Load all strategies from a directory.

        Args:
            directory: Path to the directory containing strategy files.

        Returns:
            Total number of strategies loaded.
        """
        if not directory.is_dir():
            logger.error(f"Strategy directory not found: {directory}")
            return 0

        total_loaded = 0
        for file_path in directory.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            loaded = self.load_from_file(file_path)
            total_loaded += loaded

        return total_loaded

    def _load_strategies_from_module(self, module: Any) -> int:
        """Load all BaseStrategy subclasses from a module.

        Args:
            module: Python module to scan.

        Returns:
            Number of strategies loaded.
        """
        loaded = 0
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseStrategy)
                and attr is not BaseStrategy
            ):
                try:
                    self.register(attr)
                    loaded += 1
                except ValueError as e:
                    logger.warning(f"Skipping {attr_name}: {e}")

        return loaded

    async def cleanup_all(self) -> None:
        """Cleanup all strategy instances."""
        for name, instance in self._instances.items():
            try:
                await instance.cleanup()
                logger.info(f"Cleaned up strategy: {name}")
            except Exception as e:
                logger.error(f"Error cleaning up strategy {name}: {e}")

        self._instances.clear()


# Global registry instance
_default_registry: Optional[StrategyRegistry] = None


def get_registry() -> StrategyRegistry:
    """Get the default strategy registry.

    Returns:
        The global StrategyRegistry instance.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = StrategyRegistry()
    return _default_registry
