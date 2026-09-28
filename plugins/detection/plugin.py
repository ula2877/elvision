"""Detection plugin example — shows how to create a plugin."""
from __future__ import annotations

from typing import Any

from app.core.plugins import PluginBase


class Plugin(PluginBase):
    @property
    def name(self) -> str:
        return "detection"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def description(self) -> str:
        return "Object detection plugin stub"

    def initialize(self, context: dict[str, Any]) -> bool:
        return True

    def shutdown(self) -> None:
        pass
