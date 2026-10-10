"""AssiStuff command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from assistuff import __version__
from assistuff.config import ConfigError, ensure_user_dirs, load_runtime_config
from assistuff.config.paths import get_project_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assistuff",
        description="AssiStuff Framework — local-first voice assistant",
    )
    parser.add_argument("--version", action="version", version=f"AssiStuff {__version__}")
    parser.add_argument("--check", action="store_true", help="Validate configuration and prerequisites")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--tray-only", action="store_true", help="Run tray icon only")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    parser.add_argument("--prompt", metavar="TEXT", help="Run a single text prompt through the pipeline")
    parser.add_argument("--model", metavar="ID", help="Force a specific model for --prompt")
    parser.add_argument("--audio", metavar="FILE", help="Transcribe an audio file and process it")
    parser.add_argument("--mic", action="store_true", help="Record from microphone and process")

    parser.add_argument("--list-models", action="store_true", help="List installed model manifests")
    parser.add_argument("--list-skills", action="store_true", help="List installed skill manifests")
    parser.add_argument("--list-tags", metavar="PROFILE", help="List memory tags for a profile")

    parser.add_argument("--install-pkg", metavar="FILE", help="Install a .nrdpkg package")
    parser.add_argument("--unload", metavar="MODEL", help="Unload a model from Ollama")
    parser.add_argument("--bus-test", action="store_true", help="Test Capability Bus with an echo skill")
    parser.add_argument("--memory", metavar="CMD", nargs="+",
                        help="Memory ops: search <query> | append <text> --tags a,b | tags | reindex")
    parser.add_argument("--profile", metavar="ID", help="Profile for memory ops")
    parser.add_argument("--skill", metavar="NAME", help="Call a skill directly")
    parser.add_argument("--skill-input", metavar="TEXT", default="", help="Input for --skill")
    parser.add_argument("--ask", metavar="TEXT", help="Full pipeline: route + execute + memory")
    parser.add_argument("--stream", action="store_true", help="Stream events while running --ask")

    return parser


def _setup_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def _run_check() -> int:
    try:
        ensure_user_dirs()
        config = load_runtime_config()
    except ConfigError as exc:
        print(f"[ERROR] {exc}")
        return 1

    fw = config.framework
    print(f"[OK] config loaded: framework={fw.framework.name} v{fw.framework.version}")
    print(f"[OK] project_root={config.project_root}")
    print(f"[OK] user_root={config.user_root}")
    print(f"[OK] models: {len(config.models)} — {', '.join(sorted(config.models))}")
    print(f"[OK] skills: {len(config.skills)} — {', '.join(sorted(config.skills))}")
    print(f"[OK] personalities: {len(config.personalities)}")
    print(f"[OK] pupc levels: {len(config.pupc.levels)}")

    from assistuff.runtime.ollama import OllamaClient
    client = OllamaClient(fw.runtime.ollama)
    try:
        tags = await client.list_models()
    except Exception as exc:
        print(f"[WARN] Ollama unreachable: {exc}")
    else:
        print(f"[OK] Ollama reachable, {len(tags)} models installed")
        needed = {m.runtime.tag for m in config.models.values()}
        needed |= {
            fw.runtime.utility_models.router,
            fw.runtime.utility_models.planner,
            fw.runtime.utility_models.mpa,
        }
        missing = needed - tags
        if missing:
            print(f"[WARN] models not installed in Ollama: {', '.join(sorted(missing))}")

    return 0


async def _run_prompt(text: str, model_id: str | None, debug: bool) -> int:
    from assistuff.runtime.ollama import OllamaClient
    from assistuff.runtime.model_runtime import ModelRuntime

    config = load_runtime_config()
    client = OllamaClient(config.framework.runtime.ollama)

    if model_id is None:
        model_id = config.framework.runtime.utility_models.router

    manifest = config.models.get(model_id)
    if manifest is None:
        manifest = next(
            (item for item in config.models.values() if item.runtime.tag == model_id),
            None,
        )
    if manifest is None:
        print(f"[ERROR] unknown model id: {model_id}")
        return 1

    runtime = ModelRuntime(manifest, client, config)
    try:
        response = await runtime.generate(text)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        if debug:
            raise
        return 1

    print(response)
    return 0


async def _run_unload(model: str) -> int:
    from assistuff.runtime.ollama import OllamaClient

    config = load_runtime_config()
    client = OllamaClient(config.framework.runtime.ollama)
    await client.unload(model)
    print(f"[OK] unloaded {model}")
    return 0


async def _dispatch(args: argparse.Namespace) -> int:
    if args.memory:
        return await _run_memory(args.memory, args.profile)
    if args.bus_test:
        return await _run_bus_test(args.prompt or "ping")
    if args.check:
        return await _run_check()
    if args.prompt:
        return await _run_prompt(args.prompt, args.model, args.debug)
    if args.unload:
        return await _run_unload(args.unload)
    if args.list_models:
        config = load_runtime_config()
        for mid in sorted(config.models):
            m = config.models[mid]
            caps = ", ".join(m.capabilities.provides) or "—"
            print(f"{mid}@{m.version}  [{m.runtime.tag}]  caps: {caps}")
        return 0
    if args.list_skills:
        config = load_runtime_config()
        for sid in sorted(config.skills):
            s = config.skills[sid]
            caps = ", ".join(s.capabilities.provides) or "—"
            print(f"{sid}@{s.version}  caps: {caps}")
        return 0
    if args.list_tags:
        from assistuff.memory.long_term import LongTermMemory
        from assistuff.memory.profiles import ProfileManager
        config = load_runtime_config()
        pm = ProfileManager(config.framework.profiles.storage_dir)
        profile = pm.create(args.list_tags)
        mem = LongTermMemory(pm.profile_dir(profile) / "memory.md")
        mem.load_tags()
        for tag in mem.tags.all():
            print(tag)
        return 0
    if args.skill:
        return await _run_skill(args.skill, args.skill_input, args.profile)
    if args.install_pkg:
        return await _run_install_pkg(args.install_pkg)
    if args.ask:
        return await _run_ask(args.ask, args.stream, args.profile)
    if args.tray_only:
        return _run_gui(tray_only=True, profile=args.profile)
    if not args.headless and not any(
        (
            args.memory,
            args.bus_test,
            args.check,
            args.prompt,
            args.unload,
            args.list_models,
            args.list_skills,
            args.list_tags,
            args.skill,
            args.install_pkg,
            args.ask,
            args.tray_only,
        )
    ):
        return _run_gui(tray_only=False, profile=args.profile)

    print("AssiStuff running in headless mode. GUI disabled.")
    return 0

 


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.debug)

    if args.tray_only or (
        not args.headless
        and not any(
            (
                args.memory,
                args.bus_test,
                args.check,
                args.prompt,
                args.unload,
                args.list_models,
                args.list_skills,
                args.list_tags,
                args.skill,
                args.install_pkg,
                args.ask,
            )
        )
    ):
        return _run_gui(tray_only=args.tray_only, profile=args.profile)

    try:
        return asyncio.run(_dispatch(args))
    except KeyboardInterrupt:
        return 130

    
async def _run_bus_test(text: str) -> int:
    from assistuff.bus import CapabilityBus, OutputChain, Trace
    from assistuff.bus.adapters.skill_adapter import make_skill_capability
    from assistuff.bus.emitters.log import log_emitter

    config = load_runtime_config()
    chain = OutputChain()
    chain.subscribe(log_emitter)
    bus = CapabilityBus(chain, max_hops=config.framework.runtime.max_hops)

    # Register a test skill capability
    from assistuff.skills.registry import SkillContext, Skill
    from assistuff.access.user import User

    def echo_run(value: str, _ctx: SkillContext) -> str:
        return f"echo: {value}"

    from assistuff.config.schemas import (
        ModelCapabilities, SkillImplementation, SkillManifest, SkillNetworkSpec,
        InteropSpec, AccessSpec, EmitsSpec,
    )

    manifest = SkillManifest(
        id="echo",
        version="1.0.0",
        capabilities=ModelCapabilities(provides=["echo.say"]),
        access=AccessSpec(min_level=0),
        interop=InteropSpec(accepts_calls_from=["*"], can_call=[]),
        emits=EmitsSpec(default_kind="result", can_emit=["result"]),
        network=SkillNetworkSpec(),
        implementation=SkillImplementation(
            module="assistuff.skills.builtin.echo",
            entrypoint="run",
        ),
    )
    skill = Skill(name="echo", run=echo_run)
    context = SkillContext(profile="default", memory=None, user=User(level=5, name="admin"))
    bus.register(make_skill_capability(manifest, skill, context_provider=lambda: context))

    trace = Trace(query=text)
    async for event in bus.call("echo.say", {"value": text}, caller="user", trace=trace):
        pass
    trace.finish()
    print(f"[OK] trace: {trace.summary()}")
    final = chain.final_result(trace.trace_id)
    print(f"[OK] final: {final}")
    return 0


async def _run_memory(cmd: list[str], profile_arg: str | None) -> int:
    from assistuff.memory import MemoryStore, ProfileManager
    from assistuff.memory.long_term import MemoryQuery

    config = load_runtime_config()
    pm = ProfileManager(config.framework.profiles.storage_dir)
    profile = pm.create(profile_arg or pm.get_active())
    profile_dir = pm.profile_dir(profile)
    store = MemoryStore(profile, profile_dir, config.framework.memory)

    if not cmd:
        print("usage: --memory search|append|tags|reindex ...")
        return 1

    action = cmd[0]

    if action == "tags":
        for tag in store.long_term.tags.all():
            print(tag)
        return 0

    if action == "reindex":
        store.long_term.reindex()
        print(f"[OK] reindexed {store.long_term.count()} notes")
        return 0

    if action == "search":
        if len(cmd) < 2:
            print("usage: --memory search <query>")
            return 1
        query = " ".join(cmd[1:])
        hits = store.retriever.search(query)
        for h in hits:
            print(f"{h.timestamp} {' '.join(h.tags)}: {h.text}")
        if not hits:
            print("(no results)")
        return 0

    if action == "append":
        if len(cmd) < 2:
            print("usage: --memory append <text> [--tags tag1,tag2]")
            return 1
        text_parts: list[str] = []
        tags: list[str] = []
        i = 1
        while i < len(cmd):
            if cmd[i] == "--tags":
                i += 1
                if i < len(cmd):
                    tags = [t.strip() for t in cmd[i].split(",")]
            else:
                text_parts.append(cmd[i])
            i += 1
        text = " ".join(text_parts)
        hit = store.long_term.append(text, tags or ["#misc"])
        print(f"[OK] appended: [{hit.timestamp}] {' '.join(hit.tags)} {hit.text}")
        return 0

    print(f"unknown memory action: {action}")
    return 1

async def _run_skill(name: str, text: str, profile_arg: str | None) -> int:
    from assistuff.access.user import User
    from assistuff.memory import MemoryStore, ProfileManager
    from assistuff.skills.builtin.factory import register_builtins
    from assistuff.skills.plugins.loader import load_plugins
    from assistuff.skills.registry import SkillContext, SkillRegistry

    config = load_runtime_config()
    pm = ProfileManager(config.framework.profiles.storage_dir)
    profile = pm.create(profile_arg or pm.get_active())
    store = MemoryStore(profile, pm.profile_dir(profile), config.framework.memory)

    user = User(level=4, name="admin")
    registry = SkillRegistry()
    register_builtins(registry, config.skills)
    load_plugins(
        registry,
        plugin_dir=config.framework.tasks.plugin_dir,
        enabled_plugins=config.framework.tasks.enabled_plugins,
    )

    context = SkillContext(profile=profile, memory=store, user=user)
    try:
        result = registry.get(name).run(text, context)
    except KeyError:
        print(f"[ERROR] unknown skill: {name}")
        print(f"available: {', '.join(registry.names())}")
        return 1
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(result)
    return 0

async def _run_install_pkg(path: str) -> int:
    from pathlib import Path

    from assistuff.pack import InstallError, install_package

    try:
        entry = install_package(Path(path), allow_unsigned=True)
    except InstallError as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(f"[OK] installed {entry['package_id']}@{entry['version']}")
    if entry.get("ollama_tag"):
        print(f"     ollama tag: {entry['ollama_tag']}")
    return 0

async def _run_ask(text: str, stream: bool, profile_arg: str | None) -> int:
    from assistuff.dispatch import Dispatcher

    config = load_runtime_config()
    dispatcher = Dispatcher(config, profile=profile_arg)
    try:
        if stream:
            from assistuff.bus.events import ChainEvent
            def printer(event: ChainEvent) -> None:
                preview = event.payload.get("text") or event.payload
                if isinstance(preview, str) and len(preview) > 200:
                    preview = preview[:200] + "…"
                print(f"[{event.trace_id[:8]}] {event.source} ({event.kind}): {preview}")
            dispatcher.chain.subscribe(printer)
            final = await dispatcher.final_text(text)
        else:
            final = await dispatcher.final_text(text)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    finally:
        await dispatcher.aclose()

    if not stream:
        print(final)
    return 0

def _run_gui(*, tray_only: bool, profile: str | None) -> int:
    try:
        from assistuff.ui.gui import run_gui
    except ImportError as exc:
        print(f"[ERROR] GUI dependencies missing: {exc}")
        print("        install with: pip install 'assistuff[gui]'")
        return 1
    return run_gui(tray_only=tray_only, profile=profile)


if __name__ == "__main__":
    sys.exit(main())