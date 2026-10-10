"""GUI entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

from PyQt6.QtWidgets import QApplication

from assistuff.config import load_runtime_config

from .shell import AssiStuffTray, MainWindow

logger = logging.getLogger(__name__)


def run_gui(*, tray_only: bool = False, profile: str | None = None) -> int:
    config = load_runtime_config()

    # Try to build a dispatcher (async) using a dedicated event loop
    dispatcher = None
    try:
        from assistuff.dispatch import Dispatcher
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        dispatcher = loop.run_until_complete(_build_dispatcher(config, profile))
    except Exception:
        logger.exception("failed to build dispatcher; UI runs in read-only mode")
        dispatcher = None

    app = QApplication.instance() or QApplication(sys.argv)

    window = None
    if not tray_only:
        window = MainWindow(config, dispatcher=dispatcher, profile=profile)
        window.show()

    tray = AssiStuffTray(window=window)
    tray.show()

    try:
        return app.exec()
    finally:
        if dispatcher is not None:
            try:
                asyncio.get_event_loop().run_until_complete(dispatcher.aclose())
            except Exception:
                pass


async def _build_dispatcher(config, profile: str | None):
    from assistuff.dispatch import Dispatcher
    return Dispatcher(config, profile=profile)