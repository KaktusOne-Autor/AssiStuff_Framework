from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from assistuff.access import AccountError, AccountRegistry, User
from assistuff.skills.portable import PortableSkillRepository


_MANIFEST = """\
id: infographic-helper
version: 1.0.0
kind: skill
instructions_file: SKILL.md
capabilities:
  provides: [visual.infographic]
input_schema:
  type: object
  properties:
    topic: {type: string}
  required: [topic]
  additionalProperties: false
output_schema:
  type: object
  properties:
    instructions: {type: string}
    input: {type: object}
  required: [instructions, input]
permissions: [visual.output]
"""


class PortableSkillTests(unittest.TestCase):
    def test_instruction_skill_installs_disabled_and_validates_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            accounts = AccountRegistry(root / "accounts.db")
            accounts.create_account(
                "owner",
                "a-long-test-password",
                profile="default",
            )
            admin = accounts.authenticate("owner", "a-long-test-password").user

            source = root / "source"
            source.mkdir()
            (source / "manifest.yaml").write_text(_MANIFEST, encoding="utf-8")
            (source / "SKILL.md").write_text(
                "Create a visual explanation from the supplied topic.",
                encoding="utf-8",
            )
            repository = PortableSkillRepository(root / "installed", accounts)
            installed = repository.install(source, actor=admin)
            self.assertFalse(installed.enabled)
            with self.assertRaises(AccountError):
                repository.install(source, actor=User(level=0, name="guest"))

            enabled = repository.set_enabled(
                "infographic-helper",
                True,
                actor=admin,
            )
            self.assertTrue(enabled.enabled)
            skill = repository.as_skill(enabled)
            result = json.loads(skill.run('{"topic":"solar system"}', None))
            self.assertEqual(result["input"], {"topic": "solar system"})
            self.assertIn("visual explanation", result["instructions"])
            with self.assertRaisesRegex(ValueError, "JSON Schema"):
                skill.run('{"topic": 3}', None)

    def test_manifest_cannot_escape_package_or_fetch_remote_schema_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            accounts = AccountRegistry(root / "accounts.db")
            repository = PortableSkillRepository(root / "installed", accounts)
            source = root / "source"
            source.mkdir()
            (source / "manifest.yaml").write_text(
                _MANIFEST.replace(
                    "input_schema:",
                    'input_schema:\n  "$ref": "https://example.invalid/schema.json"\n  ',
                ),
                encoding="utf-8",
            )
            (source / "SKILL.md").write_text("Instructions", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "remote JSON Schema references"):
                repository.inspect(source)


if __name__ == "__main__":
    unittest.main()
