from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assistuff.access import AccountError, AccountRegistry, User


class AccountRegistryTests(unittest.TestCase):
    def test_bootstrap_authentication_profile_binding_and_admin_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = AccountRegistry(Path(temp_dir) / "accounts.db")
            admin = registry.create_account(
                "owner",
                "a-long-test-password",
                profile="default",
            )
            self.assertEqual(admin.level, 5)

            session = registry.authenticate("OWNER", "a-long-test-password")
            self.assertTrue(session.user.authenticated)
            self.assertEqual(session.profile, "default")
            self.assertEqual(len(registry.list_accounts(session.user)), 1)

            member = registry.create_account(
                "member",
                "another-long-password",
                profile="member",
                actor=session.user,
            )
            self.assertEqual(member.level, 0)
            with self.assertRaises(AccountError):
                registry.authenticate(
                    "member",
                    "another-long-password",
                    profile="default",
                )

            member_session = registry.authenticate("member", "another-long-password")
            registry.set_level(member.account_id, 3, actor=session.user)
            refreshed = registry.authenticate("member", "another-long-password")
            self.assertEqual(refreshed.user.level, 3)

            with self.assertRaises(AccountError):
                registry.list_accounts(member_session.user)
            with self.assertRaises(AccountError):
                registry.list_accounts(
                    User(level=5, name="forged", account_id="not-an-account", authenticated=True)
                )

            registry.disable_account(member.account_id, actor=session.user)
            with self.assertRaises(AccountError):
                registry.resolve_session(member_session.user, "member")
            with self.assertRaises(AccountError):
                registry.authenticate("member", "another-long-password")

    def test_password_policy_and_last_admin_protection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = AccountRegistry(Path(temp_dir) / "accounts.db")
            with self.assertRaisesRegex(ValueError, "at least 12"):
                registry.create_account("owner", "short", profile="default")
            owner = registry.create_account(
                "owner",
                "a-long-test-password",
                profile="default",
            )
            session = registry.authenticate("owner", "a-long-test-password")
            with self.assertRaises(AccountError):
                registry.set_level(owner.account_id, 4, actor=session.user)
            with self.assertRaises(AccountError):
                registry.disable_account(owner.account_id, actor=session.user)
            with self.assertRaises(ValueError):
                registry.create_account(
                    "guest-owner",
                    "another-long-password",
                    profile="guest",
                    actor=session.user,
                )


if __name__ == "__main__":
    unittest.main()
