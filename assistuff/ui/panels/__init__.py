"""Panels for the main window."""

from .chat import ChatPanel
from .memory import MemoryPanel
from .models import ModelsPanel
from .plugins import PluginsPanel
from .settings import SettingsPanel
from .skills import SkillsPanel
from .tasks import TasksPanel
from .trace import TracePanel

__all__ = [
    "ChatPanel",
    "MemoryPanel",
    "ModelsPanel",
    "PluginsPanel",
    "SettingsPanel",
    "SkillsPanel",
    "TasksPanel",
    "TracePanel",
]