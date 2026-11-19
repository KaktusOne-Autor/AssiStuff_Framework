from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assistuff.access import AccountRegistry
from assistuff.pack.cli import _require_package_admin
from assistuff.pack.installer import InstallError


class PackageCliAccessTests(unittest.TestCase):
    def test_install_mutations_require_a_current_level_five_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = AccountRegistry(root / "accounts.db")
            owner = registry.create_account(
                "owner",
                "a-long-test-password",
                profile="default",
            )
            owner_session = registry.authenticate("owner", "a-long-test-password")
            registry.create_account(
                "member",
                "another-long-password",
                profile="member",
                actor=owner_session.user,
            )

            with patch(
                "assistuff.config.paths.get_user_root",
                return_value=root,
            ):
                with self.assertRaisesRegex(InstallError, "--admin-account"):
                    _require_package_admin(None)

                with patch("getpass.getpass", return_value="a-long-test-password"):
                    _require_package_admin("owner")

                with patch("getpass.getpass", return_value="another-long-password"):
                    with self.assertRaises(InstallError):
                        _require_package_admin("member")

            self.assertEqual(owner.level, 5)


if __name__ == "__main__":
    unittest.main()
