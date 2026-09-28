"""
Plugin system — discovers and loads plugins from a directory.
Plugins are Python packages with a `plugin.py` module containing a `Plugin` class
that inherits from `PluginBase`.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal

from app.core.logging import LogService


class PluginBase(ABC):
    """Abstract base for all plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        ...

    @property
    def description(self) -> str:
        return ""

    @abstractmethod
    def initialize(self, context: dict[str, Any]) -> bool:
        """Called once when plugin is loaded. Return False to reject."""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """Called when plugin is unloaded."""
        ...


class PluginManager(QObject):
    """Discovers, loads, and manages plugins."""

    plugin_loaded = Signal(str)  # plugin name
    plugin_unloaded = Signal(str)
    plugin_error = Signal(str, str)  # plugin name, error message

    def __init__(self, plugins_dir: str = "plugins", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._plugins_dir = Path(plugins_dir)
        self._plugins: dict[str, PluginBase] = {}
        self._log = LogService.instance()

    def discover(self) -> list[str]:
        """Scan plugin directory and return discovered plugin names."""
        discovered: list[str] = []

        if not self._plugins_dir.exists():
            self._plugins_dir.mkdir(parents=True, exist_ok=True)
            self._log.info("Created plugins directory: %s", self._plugins_dir)
            return discovered

        for child in self._plugins_dir.iterdir():
            if child.is_dir() and not child.name.startswith("_"):
                plugin_file = child / "plugin.py"
                if plugin_file.exists():
                    discovered.append(child.name)

        self._log.info("Discovered %d plugins: %s", len(discovered), discovered)
        return discovered

    def load(self, plugin_name: str) -> bool:
        """Load a single plugin by name."""
        if plugin_name in self._plugins:
            self._log.warning("Plugin %s already loaded", plugin_name)
            return True

        plugin_path = self._plugins_dir / plugin_name / "plugin.py"
        if not plugin_path.exists():
            self._log.error("Plugin file not found: %s", plugin_path)
            return False

        try:
            spec = importlib.util.spec_from_file_location(
                f"app_plugin_{plugin_name}",
                str(plugin_path),
            )
            if spec is None or spec.loader is None:
                self._log.error("Failed to create spec for %s", plugin_name)
                return False

            module = importlib.util.module_from_spec(spec)
            sys.modules[module.__name__] = module
            spec.loader.exec_module(module)

            plugin_cls = getattr(module, "Plugin", None)
            if plugin_cls is None or not issubclass(plugin_cls, PluginBase):
                self._log.error(
                    "Plugin %s must define a 'Plugin' class inheriting PluginBase", plugin_name
                )
                return False

            instance: PluginBase = plugin_cls()
            context: dict[str, Any] = {"plugins_dir": self._plugins_dir}
            if instance.initialize(context):
                self._plugins[plugin_name] = instance
                self._log.info("Plugin loaded: %s v%s", instance.name, instance.version)
                self.plugin_loaded.emit(instance.name)
                return True
            else:
                self._log.error("Plugin %s rejected during initialization", plugin_name)
                return False

        except Exception as exc:
            self._log.error("Failed to load plugin %s: %s", plugin_name, exc)
            self.plugin_error.emit(plugin_name, str(exc))
            return False

    def load_all(self) -> None:
        """Discover and load all plugins."""
        for name in self.discover():
            self.load(name)

    def unload(self, plugin_name: str) -> None:
        plugin = self._plugins.pop(plugin_name, None)
        if plugin is not None:
            try:
                plugin.shutdown()
                self.plugin_unloaded.emit(plugin_name)
                self._log.info("Plugin unloaded: %s", plugin_name)
            except Exception as exc:
                self._log.error("Error unloading plugin %s: %s", plugin_name, exc)

    def get(self, plugin_name: str) -> Optional[PluginBase]:
        return self._plugins.get(plugin_name)

    def loaded_plugins(self) -> list[str]:
        return list(self._plugins.keys())
