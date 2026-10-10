"""Plugin loader — enabled plugins only."""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from pathlib import Path

from assistuff.skills.registry import SkillContext, SkillRegistry

logger = logging.getLogger(__name__)

_PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def load_plugins(
    registry: SkillRegistry,
    *,
    plugin_dir: str | Path,
    enabled_plugins: list[str],
) -> None:
    if not enabled_plugins:
        return

    base_dir = Path(plugin_dir).resolve()
    for plugin_id in enabled_plugins:
        if not _PLUGIN_ID_RE.fullmatch(plugin_id):
            raise ValueError(f"invalid plugin id: {plugin_id!r}")

        manifest_path = (base_dir / f"{plugin_id}.json").resolve()
        module_path = (base_dir / f"{plugin_id}.py").resolve()

        if manifest_path.parent != base_dir or module_path.parent != base_dir:
            raise ValueError(f"plugin {plugin_id!r} escapes plugin dir")
        if not manifest_path.is_file() or not module_path.is_file():
            raise FileNotFoundError(
                f"plugin {plugin_id!r} requires {plugin_id}.json and {plugin_id}.py"
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        skill_name = manifest.get("skill")
        permission = manifest.get("permission")
        if not isinstance(skill_name, str) or not isinstance(permission, str):
            raise ValueError(f"plugin {plugin_id!r} manifest needs string skill and permission")

        def make_runner(plugin_name: str, path: Path):
            def runner(value: str, context: SkillContext) -> str:
                module_name = f"assistuff_plugin_{plugin_name}"
                module = sys.modules.get(module_name)
                if module is None:
                    spec = importlib.util.spec_from_file_location(module_name, path)
                    if spec is None or spec.loader is None:
                        raise ImportError(f"cannot load plugin {plugin_name!r}")
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    try:
                        spec.loader.exec_module(module)
                    except Exception:
                        del sys.modules[module_name]
                        raise
                handler = getattr(module, "run", None)
                if not callable(handler):
                    raise TypeError(f"plugin {plugin_name!r} must export run(value, context)")
                result = handler(value, context)
                if not isinstance(result, str):
                    raise TypeError(f"plugin {plugin_name!r} must return str")
                return result
            return runner

        registry.register(
            skill_name,
            make_runner(plugin_id, module_path),
            permission=permission,
            description=f"plugin:{plugin_id}",
        )
        logger.info("registered plugin %s as skill %s", plugin_id, skill_name)