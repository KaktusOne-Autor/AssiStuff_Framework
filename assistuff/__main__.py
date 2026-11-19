"""AssiStuff command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys

from assistuff import __version__
from assistuff.config import ConfigError, ensure_user_dirs, load_runtime_config
from assistuff.config.paths import get_project_root

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assistuff",
        description="AssiStuff Framework — local-first voice assistant",
    )
    parser.add_argument("--version", action="version", version=f"AssiStuff {__version__}")
    parser.add_argument(
        "--check", action="store_true", help="Validate configuration and prerequisites"
    )
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--tray-only", action="store_true", help="Run tray icon only")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    parser.add_argument(
        "--prompt", metavar="TEXT", help="Run a single text prompt through the pipeline"
    )
    parser.add_argument("--model", metavar="ID", help="Force a specific model for --prompt")
    voice_input = parser.add_mutually_exclusive_group()
    voice_input.add_argument(
        "--audio", metavar="FILE", help="Transcribe a local audio file and process it"
    )
    voice_input.add_argument(
        "--mic", action="store_true", help="Record one local microphone turn and process it"
    )

    parser.add_argument("--list-models", action="store_true", help="List installed model manifests")
    parser.add_argument("--list-skills", action="store_true", help="List installed skill manifests")
    parser.add_argument("--mcp", action="store_true", help="Serve enabled skills over MCP stdio")
    parser.add_argument(
        "--skill-install", metavar="DIR", help="Install an instruction-only portable skill"
    )
    parser.add_argument("--skill-enable", metavar="ID", help="Enable an installed portable skill")
    parser.add_argument("--skill-disable", metavar="ID", help="Disable an installed portable skill")
    parser.add_argument("--account-create", metavar="USERNAME", help="Create a local account")
    parser.add_argument(
        "--new-account-level",
        type=int,
        choices=range(6),
        default=0,
        help="PUPC level for a new non-bootstrap account",
    )
    parser.add_argument(
        "--account-list", action="store_true", help="List accounts (requires admin login)"
    )
    parser.add_argument(
        "--account-set-level", metavar="ACCOUNT_ID:LEVEL", help="Change a PUPC level"
    )
    parser.add_argument("--account-disable", metavar="ACCOUNT_ID", help="Disable an account")
    parser.add_argument(
        "--admin-account", metavar="USERNAME", help="Administrator account for account management"
    )
    parser.add_argument("--list-tags", metavar="PROFILE", help="List memory tags for a profile")
    parser.add_argument("--tags", default="", help="Comma-separated tags for --memory append")
    parser.add_argument("--force", action="store_true", help="Force a memory index rebuild")

    parser.add_argument("--install-pkg", metavar="FILE", help="Install a .nrdpkg package")
    parser.add_argument("--unload", metavar="MODEL", help="Unload a model from Ollama")
    parser.add_argument(
        "--bus-test", action="store_true", help="Test Capability Bus with an echo skill"
    )
    parser.add_argument(
        "--memory",
        metavar="CMD",
        nargs="+",
        help="Memory ops: search <query> | append <text> --tags a,b | tags | audit-tags | reindex",
    )
    parser.add_argument("--profile", metavar="ID", help="Profile for memory ops")
    parser.add_argument(
        "--account", metavar="USERNAME", help="Authenticate CLI operation as an account"
    )
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
    from assistuff.voice.pipeline import VoicePipeline

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
    voice = VoicePipeline(
        fw.voice,
        project_root=config.project_root,
        user_root=config.user_root,
        profile=fw.profiles.default,
    )
    for stage, (ready, detail) in voice.diagnostics().items():
        label = "OK" if ready else "WARN"
        print(f"[{label}] voice {stage}: {detail}")

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


async def _run_voice_input(
    *,
    audio_path: str | None,
    account_username: str | None,
    profile_arg: str | None,
) -> int:
    from assistuff.access import AccountError
    from assistuff.dispatch import Dispatcher
    from assistuff.voice.common import VoiceError

    config = load_runtime_config()
    try:
        user, profile = _cli_identity(
            config,
            account_username=account_username,
            profile_arg=profile_arg,
        )
    except (AccountError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    dispatcher = Dispatcher(config, profile=profile, user=user)
    try:
        if (
            config.framework.voice.auth.enabled
            and not dispatcher.voice.auth.has_voiceprint(profile)
        ):
            raise VoiceError(
                f"no voiceprint is enrolled for profile {profile!r}; "
                "enroll it in the Chat tab before using voice input"
            )
        failures = await dispatcher.initialize()
        for model, error in failures.items():
            print(f"[WARN] model {model} could not be initialized: {error}")
        if audio_path:
            transcript = await dispatcher.voice.transcribe_file(audio_path)
        else:
            transcript = await asyncio.to_thread(dispatcher.voice.capture)
            transcript = await dispatcher.voice.transcribe_clip(transcript)
        print(f"[voice] {transcript}")
        response = await dispatcher.final_text(transcript)
        print(response)
        if config.framework.voice.tts.enabled:
            try:
                await asyncio.to_thread(dispatcher.voice.tts.speak, response)
            except VoiceError as exc:
                print(f"[WARN] speech output unavailable: {exc}")
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    finally:
        await dispatcher.aclose()
    return 0


async def _run_prompt(
    text: str,
    model_id: str | None,
    debug: bool,
    *,
    account_username: str | None = None,
    profile_arg: str | None = None,
) -> int:
    from assistuff.access import Pupc
    from assistuff.runtime.ollama import OllamaClient
    from assistuff.runtime.model_runtime import ModelRuntime
    from assistuff.runtime.residency import ModelResidency
    from assistuff.runtime.remote_api import OpenAICompatibleClient

    config = load_runtime_config()
    try:
        user, _ = _cli_identity(
            config,
            account_username=account_username,
            profile_arg=profile_arg,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"[ERROR] {exc}")
        return 1

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

    client = OllamaClient(config.framework.runtime.ollama)
    remote_client = None
    if manifest.access:
        try:
            Pupc(config.framework.access, config.pupc).enforce(
                user,
                manifest.access.min_level,
                action=f"model:{manifest.id}",
            )
        except PermissionError as exc:
            print(f"[ERROR] {exc}")
            await client.aclose()
            return 1
    if manifest.runtime.backend == "remote_api":
        profile = manifest.runtime.endpoint_profile
        if profile is None or profile not in config.framework.runtime.remote_endpoints:
            print(f"[ERROR] remote endpoint profile is missing for {manifest.id}")
            await client.aclose()
            return 1
        remote_client = OpenAICompatibleClient(config.framework.runtime.remote_endpoints[profile])
    runtime = ModelRuntime(manifest, client, config, remote_client=remote_client)
    try:
        if manifest.runtime.backend != "remote_api":
            residency = ModelResidency(client, config)
            await residency.ensure_loaded(manifest.runtime.tag)
        response = await runtime.generate(text)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        if debug:
            raise
        return 1
    finally:
        if remote_client is not None:
            await remote_client.aclose()
        await client.aclose()

    print(response)
    return 0


async def _run_unload(model: str, admin_username: str | None = None) -> int:
    from assistuff.runtime.ollama import OllamaClient

    try:
        _require_local_admin(admin_username)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1
    config = load_runtime_config()
    client = OllamaClient(config.framework.runtime.ollama)
    await client.unload(model)
    print(f"[OK] unloaded {model}")
    return 0


async def _dispatch(args: argparse.Namespace) -> int:
    if args.mcp:
        return await _run_mcp(
            account_username=args.account,
            profile_arg=args.profile,
        )
    if args.account_create:
        return _run_account_create(
            args.account_create,
            admin_username=args.admin_account,
            profile=args.profile,
            level=args.new_account_level,
        )
    if args.account_list:
        return _run_account_list(args.admin_account)
    if args.account_set_level:
        return _run_account_set_level(args.account_set_level, args.admin_account)
    if args.account_disable:
        return _run_account_disable(args.account_disable, args.admin_account)
    if args.skill_install:
        return _run_portable_skill_install(args.skill_install, args.admin_account)
    if args.skill_enable:
        return _run_portable_skill_toggle(args.skill_enable, True, args.admin_account)
    if args.skill_disable:
        return _run_portable_skill_toggle(args.skill_disable, False, args.admin_account)
    if args.memory:
        return await _run_memory(
            args.memory,
            args.profile,
            account_username=args.account,
            tags_arg=args.tags,
            force=args.force,
        )
    if args.bus_test:
        return await _run_bus_test(args.prompt or "ping")
    if args.check:
        return await _run_check()
    if args.audio or args.mic:
        if args.prompt or args.ask or args.skill:
            print("[ERROR] use --audio or --mic as the only request input")
            return 2
        return await _run_voice_input(
            audio_path=args.audio,
            account_username=args.account,
            profile_arg=args.profile,
        )
    if args.prompt:
        return await _run_prompt(
            args.prompt,
            args.model,
            args.debug,
            account_username=args.account,
            profile_arg=args.profile,
        )
    if args.unload:
        return await _run_unload(args.unload, args.admin_account)
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
        from assistuff.access import AccountRegistry
        from assistuff.skills.portable import PortableSkillRepository

        repository = PortableSkillRepository(
            config.user_root / "skills",
            AccountRegistry(config.user_root / "accounts.db"),
        )
        for package in repository.installed():
            state = "enabled" if package.enabled else "disabled"
            caps = ", ".join(package.manifest.capabilities.provides) or "—"
            print(f"{package.manifest.id}@{package.manifest.version} [{state}] caps: {caps}")
        return 0
    if args.list_tags:
        from assistuff.memory.long_term import LongTermMemory
        from assistuff.memory.profiles import ProfileManager

        config = load_runtime_config()
        try:
            _, profile = _cli_identity(
                config,
                account_username=args.account,
                profile_arg=args.list_tags,
            )
        except (ValueError, RuntimeError) as exc:
            print(f"[ERROR] {exc}")
            return 1
        pm = ProfileManager(config.framework.profiles.storage_dir)
        mem = LongTermMemory(pm.profile_dir(profile) / "memory.md")
        mem.load_tags()
        for tag in mem.tags.all():
            print(tag)
        return 0
    if args.skill:
        return await _run_skill(
            args.skill,
            args.skill_input,
            args.profile,
            account_username=args.account,
        )
    if args.install_pkg:
        return await _run_install_pkg(args.install_pkg, args.admin_account)
    if args.ask:
        return await _run_ask(
            args.ask,
            args.stream,
            args.profile,
            account_username=args.account,
        )
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
            args.mcp,
            args.account_create,
            args.account_list,
            args.account_set_level,
            args.account_disable,
            args.skill_install,
            args.skill_enable,
            args.skill_disable,
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
                args.mcp,
                args.account_create,
                args.account_list,
                args.account_set_level,
                args.account_disable,
                args.skill_install,
                args.skill_enable,
                args.skill_disable,
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


def _account_setup():
    from assistuff.access import AccountRegistry

    config = load_runtime_config()
    registry = AccountRegistry(config.user_root / "accounts.db")
    return config, registry


def _portable_skill_repository(config):
    from assistuff.access import AccountRegistry
    from assistuff.skills.portable import PortableSkillRepository

    return PortableSkillRepository(
        config.user_root / "skills",
        AccountRegistry(config.user_root / "accounts.db"),
    )


def _admin_account(registry, username: str | None):
    from getpass import getpass

    from assistuff.access import AccountError

    if not username:
        raise AccountError("specify --admin-account for this operation")
    session = registry.authenticate(username, getpass("Administrator password: "))
    if session.user.level < 5:
        raise AccountError("an administrator account is required")
    return session.user


def _require_local_admin(username: str | None) -> None:
    _, registry = _account_setup()
    if registry.has_accounts():
        _admin_account(registry, username)


def _run_portable_skill_install(source: str, admin_username: str | None) -> int:
    from assistuff.access import AccountError

    try:
        config, accounts = _account_setup()
        actor = _admin_account(accounts, admin_username)
        package = _portable_skill_repository(config).install(source, actor=actor)
    except (AccountError, OSError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(
        f"[OK] installed {package.manifest.id}@{package.manifest.version} "
        "disabled by default; review then enable it"
    )
    return 0


def _run_portable_skill_toggle(
    skill_id: str,
    enabled: bool,
    admin_username: str | None,
) -> int:
    from assistuff.access import AccountError

    try:
        config, accounts = _account_setup()
        actor = _admin_account(accounts, admin_username)
        package = _portable_skill_repository(config).set_enabled(
            skill_id,
            enabled,
            actor=actor,
        )
    except (AccountError, OSError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    state = "enabled" if package.enabled else "disabled"
    print(f"[OK] {package.manifest.id} is {state}; restart AssiStuff to apply")
    return 0


def _run_account_create(
    username: str,
    *,
    admin_username: str | None,
    profile: str | None,
    level: int,
) -> int:
    from getpass import getpass

    from assistuff.access import AccountError
    from assistuff.memory.profiles import ProfileManager

    try:
        config, registry = _account_setup()
        actor = _admin_account(registry, admin_username) if registry.has_accounts() else None
        password = getpass("New account password: ")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise AccountError("passwords do not match")
        selected_profile = profile or (
            "default" if not registry.has_accounts() else _account_profile_id(username)
        )
        profiles = ProfileManager(
            config.framework.profiles.storage_dir,
            config.framework.profiles.default,
        )
        profiles.create(selected_profile)
        account = registry.create_account(
            username,
            password,
            profile=selected_profile,
            level=level,
            actor=actor,
        )
    except (AccountError, ValueError, OSError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(
        f"[OK] created {account.username} (PUPC level {account.level}), profile={selected_profile}"
    )
    return 0


def _run_account_list(admin_username: str | None) -> int:
    from assistuff.access import AccountError

    try:
        _, registry = _account_setup()
        actor = _admin_account(registry, admin_username)
        accounts = registry.list_accounts(actor)
    except (AccountError, ValueError, OSError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    for account in accounts:
        state = "enabled" if account.enabled else "disabled"
        print(
            f"{account.account_id}  {account.username}  level={account.level}  "
            f"profiles={','.join(account.profiles)}  {state}"
        )
    return 0


def _run_account_set_level(value: str, admin_username: str | None) -> int:
    from assistuff.access import AccountError

    try:
        account_id, level_text = value.rsplit(":", 1)
        level = int(level_text)
        _, registry = _account_setup()
        actor = _admin_account(registry, admin_username)
        registry.set_level(account_id, level, actor=actor)
    except (AccountError, ValueError, OSError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(f"[OK] set PUPC level {level} for account {account_id}")
    return 0


def _run_account_disable(account_id: str, admin_username: str | None) -> int:
    from assistuff.access import AccountError

    try:
        _, registry = _account_setup()
        actor = _admin_account(registry, admin_username)
        registry.disable_account(account_id, actor=actor)
    except (AccountError, ValueError, OSError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(f"[OK] disabled account {account_id}")
    return 0


def _account_profile_id(username: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", username.strip().casefold()).strip("-_")
    if not normalized or not normalized[0].isalnum():
        normalized = f"user-{normalized}"
    return normalized[:32]


async def _run_mcp(
    *,
    account_username: str | None,
    profile_arg: str | None,
) -> int:
    from assistuff.access import AccountError
    from assistuff.dispatch import Dispatcher
    from assistuff.interop.mcp_server import McpToolServer

    config = load_runtime_config()
    try:
        user, profile = _cli_identity(
            config,
            account_username=account_username,
            profile_arg=profile_arg,
        )
    except (AccountError, ValueError) as exc:
        logger.error("MCP identity setup failed: %s", exc)
        return 1

    dispatcher = Dispatcher(config, profile=profile, user=user)
    try:
        failures = await dispatcher.initialize()
        for model, error in failures.items():
            logger.warning("model %s failed to initialize: %s", model, error)
        await McpToolServer(dispatcher).serve_stdio()
    except Exception:
        logger.exception("MCP server failed")
        return 1
    finally:
        await dispatcher.aclose()
    return 0


def _cli_identity(
    config,
    *,
    account_username: str | None,
    profile_arg: str | None,
):
    from getpass import getpass

    from assistuff.access import AccountError, AccountRegistry, User
    from assistuff.memory.profiles import ProfileManager

    registry = AccountRegistry(config.user_root / "accounts.db")
    if registry.has_accounts():
        if not account_username:
            if profile_arg:
                raise AccountError("selecting a profile requires authentication; use --account")
            return User(), "guest"
        session = registry.authenticate(
            account_username,
            getpass(f"Password for {account_username}: "),
            profile=profile_arg,
        )
        return session.user, session.profile

    profiles = ProfileManager(
        config.framework.profiles.storage_dir,
        config.framework.profiles.default,
    )
    return User(), profiles.create(profile_arg or profiles.get_active())


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
        ModelCapabilities,
        SkillImplementation,
        SkillManifest,
        SkillNetworkSpec,
        InteropSpec,
        AccessSpec,
        EmitsSpec,
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


async def _run_memory(
    cmd: list[str],
    profile_arg: str | None,
    *,
    account_username: str | None = None,
    tags_arg: str = "",
    force: bool = False,
) -> int:
    from assistuff.memory import MemoryStore, ProfileManager
    from assistuff.memory.long_term import MemoryQuery

    config = load_runtime_config()
    try:
        _, profile = _cli_identity(
            config,
            account_username=account_username,
            profile_arg=profile_arg,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    pm = ProfileManager(config.framework.profiles.storage_dir)
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

    if action == "audit-tags":
        counts, unknown = store.long_term.audit_tags()
        for tag, count in counts.items():
            suffix = " (unknown)" if tag in unknown else ""
            print(f"{tag}: {count}{suffix}")
        if not counts:
            print("(no tags found)")
        return 1 if unknown else 0

    if action == "reindex":
        store.long_term.reindex(force=force)
        print(f"[OK] reindexed {store.long_term.count()} notes")
        return 0

    if action == "search":
        if len(cmd) < 2:
            print("usage: --memory search <query>")
            return 1
        query = " ".join(cmd[1:])
        tags_config = config.framework.memory.long_term.tags
        retry_callback = None
        client = None
        if tags_config.search_on_unknown_tag == "retry" and tags_config.max_retries:
            from assistuff.memory.retrieval import retry_unknown_tags_with_planner
            from assistuff.runtime.ollama import OllamaClient
            from assistuff.runtime.residency import ModelResidency
            from assistuff.runtime.utility import UtilityRoles

            client = OllamaClient(config.framework.runtime.ollama)
            roles = UtilityRoles(
                client,
                config,
                residency=ModelResidency(client, config),
            )

            async def retry_callback(unknown, known):
                return await retry_unknown_tags_with_planner(roles, unknown, known)

        try:
            hits = await store.retriever.search_with_retry_async(
                query,
                retry_callback=retry_callback,
                max_retries=tags_config.max_retries,
            )
        finally:
            if client is not None:
                await client.aclose()
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
        tags: list[str] = [tag.strip() for tag in tags_arg.split(",") if tag.strip()]
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


async def _run_skill(
    name: str,
    text: str,
    profile_arg: str | None,
    *,
    account_username: str | None = None,
) -> int:
    from assistuff.access import Pupc
    from assistuff.access import AccountRegistry
    from assistuff.memory import MemoryStore, ProfileManager
    from assistuff.skills.portable import PortableSkillRepository
    from assistuff.skills.builtin.factory import register_builtins
    from assistuff.skills.plugins.loader import load_plugins
    from assistuff.skills.registry import SkillContext, SkillRegistry

    config = load_runtime_config()
    try:
        user, profile = _cli_identity(
            config,
            account_username=account_username,
            profile_arg=profile_arg,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    pm = ProfileManager(config.framework.profiles.storage_dir)
    store = MemoryStore(profile, pm.profile_dir(profile), config.framework.memory)

    registry = SkillRegistry()
    register_builtins(registry, config.skills)
    load_plugins(
        registry,
        plugin_dir=config.framework.tasks.plugin_dir,
        enabled_plugins=config.framework.tasks.enabled_plugins,
    )
    portable = PortableSkillRepository(
        config.user_root / "skills",
        AccountRegistry(config.user_root / "accounts.db"),
    )
    portable_manifests = {}
    for package in portable.enabled():
        try:
            registry.register(
                package.manifest.id,
                portable.as_skill(package),
                description="portable-instructions",
            )
            portable_manifests[package.manifest.id] = package.manifest
        except ValueError as exc:
            logger.warning("skip portable skill %s: %s", package.manifest.id, exc)

    context = SkillContext(profile=profile, memory=store, user=user)
    try:
        skill = registry.get(name)
        manifest = config.skills.get(name) or portable_manifests.get(name)
        if manifest and manifest.access:
            Pupc(config.framework.access, config.pupc).enforce(
                user,
                manifest.access.min_level,
                action=f"skill:{name}",
            )
        result = skill.run(text, context)
    except KeyError:
        print(f"[ERROR] unknown skill: {name}")
        print(f"available: {', '.join(registry.names())}")
        return 1
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(result)
    return 0


async def _run_install_pkg(path: str, admin_username: str | None = None) -> int:
    from pathlib import Path

    from assistuff.access import AccountError
    from assistuff.pack import InstallError, install_package

    try:
        _require_local_admin(admin_username)
        entry = install_package(Path(path), allow_unsigned=True)
    except (AccountError, InstallError, OSError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(f"[OK] installed {entry['package_id']}@{entry['version']}")
    if entry.get("ollama_tag"):
        print(f"     ollama tag: {entry['ollama_tag']}")
    return 0


async def _run_ask(
    text: str,
    stream: bool,
    profile_arg: str | None,
    *,
    account_username: str | None = None,
) -> int:
    from assistuff.access import AccountError
    from assistuff.dispatch import Dispatcher

    config = load_runtime_config()
    try:
        user, profile = _cli_identity(
            config,
            account_username=account_username,
            profile_arg=profile_arg,
        )
    except (AccountError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    dispatcher = Dispatcher(config, profile=profile, user=user)
    try:
        failures = await dispatcher.initialize()
        for model, error in failures.items():
            print(f"[WARN] background model {model} could not be loaded: {error}")
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
