"""GUI shell."""

from .context import UiContext
from .main_window import MainWindow, build_default_registry
from .tab_registry import TabEntry, TabRegistry
from .tray import AssiStuffTray

__all__ = [
    "AssiStuffTray",
    "MainWindow",
    "TabEntry",
    "TabRegistry",
    "UiContext",
    "build_default_registry",
]