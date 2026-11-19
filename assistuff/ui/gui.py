"""GUI entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox

from assistuff.access import AccountError, AccountRegistry, AccountSession, User
from assistuff.config import load_runtime_config

from .shell import AssiStuffTray, MainWindow

logger = logging.getLogger(__name__)


def run_gui(*, tray_only: bool = False, profile: str | None = None) -> int:
    config = load_runtime_config()
    app = QApplication.instance() or QApplication(sys.argv)
    accounts = AccountRegistry(config.user_root / "accounts.db")
    registered_accounts = accounts.has_accounts()
    session = _prompt_account_login(accounts, profile)
    user = session.user if session else User()
    active_profile = (
        session.profile
        if session
        else ("guest" if registered_accounts else profile)
    )

    if not registered_accounts:
        QMessageBox.information(
            None,
            "Guest session",
            "No accounts are registered. AssiStuff is running as a level-0 guest. "
            "Create the first administrator with `assistuff --account-create <name>`.",
        )

    # Try to build a dispatcher (async) using a dedicated event loop
    dispatcher = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        dispatcher = loop.run_until_complete(
            _build_dispatcher(config, active_profile, user)
        )
    except Exception:
        logger.exception("failed to build dispatcher; UI runs in read-only mode")
        dispatcher = None

    app = QApplication.instance() or QApplication(sys.argv)

    window = None
    if not tray_only:
        window = MainWindow(
            config,
            dispatcher=dispatcher,
            profile=active_profile,
            user=user,
        )
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


def _prompt_account_login(
    registry: AccountRegistry,
    profile: str | None,
) -> AccountSession | None:
    if not registry.has_accounts():
        return None
    for _ in range(3):
        username, accepted = QInputDialog.getText(None, "Sign in", "Account name:")
        if not accepted:
            return None
        password, accepted = QInputDialog.getText(
            None,
            "Sign in",
            "Password:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return None
        try:
            return registry.authenticate(username, password, profile=profile)
        except (AccountError, ValueError) as exc:
            QMessageBox.warning(None, "Sign-in failed", str(exc))
    QMessageBox.warning(
        None,
        "Guest session",
        "Sign-in attempts were exhausted. Continuing with level-0 guest access.",
    )
    return None


async def _build_dispatcher(config, profile: str | None, user: User):
    from assistuff.dispatch import Dispatcher
    dispatcher = Dispatcher(config, profile=profile, user=user)
    failures = await dispatcher.initialize()
    if failures:
        logger.warning(
            "some startup models did not load: %s",
            "; ".join(f"{model}: {error}" for model, error in failures.items()),
        )
    return dispatcher