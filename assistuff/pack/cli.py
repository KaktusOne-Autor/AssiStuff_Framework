"""assistuff-pack CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from assistuff import __version__
from assistuff.config.paths import get_keys_dir

from .builder import BuildError, build_package
from .installer import (
    InstallError,
    install_package,
    list_installed,
    uninstall_package,
)
from .signer import SigningError, generate_keypair


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assistuff-pack",
        description="AssiStuff package builder",
    )
    parser.add_argument("--version", action="version", version=f"assistuff-pack {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="scaffold a new package")
    p_init.add_argument("directory", type=Path)
    p_init.add_argument("--id", required=True)
    p_init.add_argument("--name", default=None)
    p_init.add_argument("--version", default="1.0.0")
    p_init.add_argument("--author", default="unknown")
    p_init.add_argument("--license", default="unknown")
    p_init.add_argument("--weights-from", action="append", default=[])

    p_build = sub.add_parser("build", help="build .nrdpkg from source dir")
    p_build.add_argument("source", type=Path)
    p_build.add_argument("-o", "--output", type=Path, default=Path("dist"))
    p_build.add_argument("--compress", choices=["zstd", "gz", "none"], default="zstd")
    p_build.add_argument("--threads", type=int, default=8)
    p_build.add_argument("--sign-key", type=Path, default=None)
    p_build.add_argument("--weights-from", default=None)

    p_lint = sub.add_parser("lint", help="validate manifest without building")
    p_lint.add_argument("path", type=Path)

    p_verify = sub.add_parser("verify", help="verify a .nrdpkg")
    p_verify.add_argument("path", type=Path)
    p_verify.add_argument("--public-key", type=Path, default=None)

    p_sign = sub.add_parser("sign", help="sign a .nrdpkg")
    p_sign.add_argument("path", type=Path)
    p_sign.add_argument("--key", type=Path, required=True)

    p_install = sub.add_parser("install", help="install a .nrdpkg")
    p_install.add_argument("path", type=Path)
    p_install.add_argument("--allow-unsigned", action="store_true")
    p_install.add_argument("--public-key", type=Path, default=None)
    p_install.add_argument("--no-verify", action="store_true")
    p_install.add_argument("--ollama-host", default="http://localhost:11434")

    sub.add_parser("list", help="list installed packages")

    p_uninstall = sub.add_parser("uninstall", help="uninstall a package")
    p_uninstall.add_argument("package_id")
    p_uninstall.add_argument("--version", default=None)

    p_keys = sub.add_parser("keys", help="key management")
    p_keys.add_argument("action", choices=["generate", "list"])
    p_keys.add_argument("--name", default="default")

    p_export = sub.add_parser("export", help="export installed package back to files")
    p_export.add_argument("package_id")
    p_export.add_argument("--version", default=None)
    p_export.add_argument("--to", type=Path, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "build":
            return _cmd_build(args)
        if args.command == "lint":
            return _cmd_lint(args)
        if args.command == "verify":
            return _cmd_verify(args)
        if args.command == "sign":
            return _cmd_sign(args)
        if args.command == "install":
            return _cmd_install(args)
        if args.command == "list":
            return _cmd_list(args)
        if args.command == "uninstall":
            return _cmd_uninstall(args)
        if args.command == "keys":
            return _cmd_keys(args)
        if args.command == "export":
            return _cmd_export(args)
    except (BuildError, InstallError, SigningError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 0


def _cmd_init(args) -> int:
    import yaml
    from .manifest import PackageManifest

    directory = args.directory
    directory.mkdir(parents=True, exist_ok=True)

    manifest = {
        "package": {
            "id": args.id,
            "name": args.name or args.id,
            "version": args.version,
            "author": args.author,
            "license": args.license,
            "noredur_api": ">=4.1.0",
        },
        "weights": {
            "bundled": True,
            "format": "gguf",
            "quantization": "Q4_K_M",
        },
        "runtime": {
            "backend": "ollama",
            "load_from": "bundled",
            "context_window": 8192,
            "temperature": 0.2,
        },
        "capabilities": {"provides": [], "requires": []},
        "interop": {"accepts_calls_from": ["*"], "can_call": []},
        "access": {"min_level": 0, "pupc_required": False},
        "provenance": {"redistribution": "allowed"},
    }
    (directory / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # Validate
    PackageManifest.model_validate(manifest)

    (directory / "prompts").mkdir(exist_ok=True)
    (directory / "schemas").mkdir(exist_ok=True)
    (directory / "weights").mkdir(exist_ok=True)
    (directory / "README.md").write_text(f"# {args.name or args.id}\n", encoding="utf-8")

    print(f"[OK] scaffolded package at {directory}")
    for spec in args.weights_from:
        print(f"     weights source: {spec}")
    return 0


def _cmd_build(args) -> int:
    pkg = build_package(
        args.source,
        args.output,
        compress=args.compress,
        threads=args.threads,
        sign_key=args.sign_key,
        weights_spec=args.weights_from,
    )
    print(f"[OK] built {pkg}")
    return 0


def _cmd_lint(args) -> int:
    import yaml
    from .manifest import PackageManifest

    path = args.path
    manifest_path = path / "manifest.yaml" if path.is_dir() else path
    if not manifest_path.is_file():
        print(f"[ERROR] manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    try:
        PackageManifest.model_validate(data)
    except Exception as exc:
        print(f"[ERROR] invalid manifest: {exc}", file=sys.stderr)
        return 1
    print(f"[OK] manifest is valid: {manifest_path}")
    return 0


def _cmd_verify(args) -> int:
    from .installer import _extract_and_validate, _verify_or_raise, _verify_weights
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        manifest = _extract_and_validate(args.path, staging)
        _verify_weights(staging, manifest)
        if args.public_key:
            _verify_or_raise(staging, args.public_key)
    print(f"[OK] package verified: {args.path}")
    return 0


def _cmd_sign(args) -> int:
    print("[INFO] in-place signing not yet implemented; use --sign-key with build")
    return 0


def _cmd_install(args) -> int:
    entry = install_package(
        args.path,
        allow_unsigned=args.allow_unsigned,
        verify_signature=not args.no_verify,
        public_key_path=args.public_key,
        ollama_host=args.ollama_host,
    )
    print(f"[OK] installed {entry['package_id']}@{entry['version']}")
    print(f"     path: {entry['path']}")
    if entry.get("ollama_tag"):
        print(f"     ollama tag: {entry['ollama_tag']}")
    return 0


def _cmd_list(args) -> int:
    registry = list_installed()
    if not registry:
        print("(no packages installed)")
        return 0
    for pkg_id, info in sorted(registry.items()):
        active = info.get("active", "?")
        for version, entry in info.get("versions", {}).items():
            marker = "*" if version == active else " "
            size = entry.get("size_bytes", 0)
            print(f"{marker} {pkg_id}@{version}  ({size / 1e9:.2f} GB)")
    return 0


def _cmd_uninstall(args) -> int:
    uninstall_package(args.package_id, args.version)
    print(f"[OK] uninstalled {args.package_id}")
    return 0


def _cmd_keys(args) -> int:
    key_dir = get_keys_dir()
    if args.action == "generate":
        priv, pub = generate_keypair(key_dir, args.name)
        print(f"[OK] generated: {priv}")
        print(f"     public: {pub}")
        return 0
    if args.action == "list":
        key_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(key_dir.glob("*.pub")):
            print(path.stem)
        return 0
    return 0


def _cmd_export(args) -> int:
    import shutil
    registry = list_installed()
    if args.package_id not in registry:
        print(f"[ERROR] package not installed: {args.package_id}", file=sys.stderr)
        return 1
    info = registry[args.package_id]
    version = args.version or info.get("active")
    if not version or version not in info["versions"]:
        print(f"[ERROR] version not installed: {version}", file=sys.stderr)
        return 1
    src = Path(info["versions"][version]["path"])
    if not src.is_dir():
        print(f"[ERROR] installed path missing: {src}", file=sys.stderr)
        return 1
    args.to.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = args.to / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    print(f"[OK] exported {args.package_id}@{version} to {args.to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())