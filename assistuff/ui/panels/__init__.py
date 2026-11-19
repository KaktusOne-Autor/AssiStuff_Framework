"""Panels for the main window."""

from .chat import ChatPanel
from .graph import GraphPanel
from .memory import MemoryPanel
from .models import ModelsPanel
from .plugins import PluginsPanel
from .settings import SettingsPanel
from .skills import SkillsPanel
from .tasks import TasksPanel
from .trace import TracePanel
from .visual_output import VisualOutputPanel
from .vtt import VttPanel

__all__ = [
    "ChatPanel",
    "GraphPanel",
    "MemoryPanel",
    "ModelsPanel",
    "PluginsPanel",
    "SettingsPanel",
    "SkillsPanel",
    "TasksPanel",
    "TracePanel",
    "VisualOutputPanel",
    "VttPanel",
]