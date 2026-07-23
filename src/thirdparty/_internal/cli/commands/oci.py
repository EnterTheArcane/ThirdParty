import argparse
import os
import sys
from pathlib import Path

from thirdparty._internal.cli._recipes import resolve_names
from thirdparty._internal.cli.command import command
from thirdparty._internal.graph import package_root
from thirdparty._internal.loader import (
    compute_package_id,
    resolve_version,
    try_load_recipe_class,
)
from thirdparty._internal.pack import gather_meta
from thirdparty._internal.pack.oci import OciBackend
from thirdparty._internal.pack.registry import OciRegistryClient
from thirdparty.errors import RecipeException


def _add_platform_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "recipe", metavar="<recipe>", nargs="*",
        help="Recipe name(s) or glob pattern(s) (default: all)")
    p.add_argument(
        "--build-type", default="Release", choices=["Debug", "Release", "RelWithDebInfo"],
        dest="build_type", metavar="<type>")
    p.add_argument(
        "--target-os", default=None, dest="target_os", metavar="<os>",
        help="Target OS whose build to act on (default: build machine)")
    p.add_argument(
        "--target-arch", default=None, dest="target_arch", metavar="<arch>",
        help="Target architecture (X64 or ARM) whose build to act on (default: build machine)")


def _add_registry_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--registry", default="ghcr.io",
        help="OCI registry host (default: ghcr.io; e.g. docker.io, quay.io, a self-hosted host)")
    p.add_argument(
        "--owner", default=None,
        help="Registry owner/org/namespace (default: $GITHUB_REPOSITORY_OWNER)")
    p.add_argument(
        "--prefix", default="thirdparty", help="Repository prefix (default: thirdparty)")
    p.add_argument(
        "--tag", default=None, help="Image tag (default: the package version)")
    p.add_argument(
        "--username", default=None,
        help="Registry username (else GH_TOKEN for ghcr.io, REGISTRY_* env, ~/.docker/config.json, netrc)")
    p.add_argument(
        "--password", default=None,
        help="Registry password or access token (pairs with --username)")
    p.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Print the planned registry calls without pushing")


def setup_parser(p: argparse.ArgumentParser) -> None:
    subs = p.add_subparsers(dest="oci_command", metavar="<subcommand>")
    subs.required = True

    build_p = subs.add_parser(
        "build", help="Build an OCI image layout on disk from a staged package")
    _add_platform_args(build_p)
    build_p.add_argument(
        "--output", default=None, dest="output", metavar="<dir>",
        help="Layout output directory (default: build/<name>/<package_id>/dist/oci)")

    push_p = subs.add_parser(
        "push", help="Push a built OCI image layout to a registry (run 'oci build' first)")
    _add_platform_args(push_p)
    _add_registry_args(push_p)
    push_p.add_argument(
        "--output", default=None, dest="output", metavar="<dir>",
        help="Layout directory to push (default: build/<name>/<package_id>/dist/oci)")

    combine_p = subs.add_parser(
        "combine", help="Assemble the multi-arch <tag> index from per-platform tags in the registry")
    combine_p.add_argument(
        "recipe", metavar="<recipe>", nargs="*",
        help="Recipe name(s) or glob pattern(s) (default: all)")
    _add_registry_args(combine_p)


@command(name="oci")
def oci(args: argparse.Namespace) -> None:
    """Build, push, and combine OCI images (build a layout on disk, then push it to a registry)."""
    handlers = {"build": _build, "push": _push, "combine": _combine}
    handlers[args.oci_command](args)


def _project() -> "tuple[Path, Path]":
    cwd = Path.cwd()
    recipes_root = cwd / "recipes"
    if not recipes_root.exists():
        print(f"[thirdparty] error: no 'recipes/' directory in {cwd}", file=sys.stderr)
        sys.exit(1)
    return recipes_root, cwd / "build"


def _layout_dir(build_root: Path, name: str, package_id: str, output: "str | None") -> Path:
    if output:
        return Path(output)
    return package_root(build_root, name, package_id) / "dist" / "oci"


def _build(args: argparse.Namespace) -> None:
    recipes_root, build_root = _project()
    names = resolve_names(recipes_root, args.recipe)
    backend = OciBackend()
    failures = 0
    for name in names:
        try:
            meta, staged = gather_meta(
                recipes_root, build_root, name, args.build_type,
                args.target_os, args.target_arch)
        except RecipeException as exc:
            print(f"[thirdparty] error: {exc}", file=sys.stderr)
            failures += 1
            continue
        out = _layout_dir(build_root, name, meta.package_id, args.output)
        produced = backend.pack(staged, out, meta)
        print(str(produced.resolve()))
    if failures:
        sys.exit(1)


def _push(args: argparse.Namespace) -> None:
    recipes_root, build_root = _project()
    owner = _require_owner(args)
    names = resolve_names(recipes_root, args.recipe)
    failures = 0
    for name in names:
        cls = try_load_recipe_class(recipes_root, name)
        if cls is None:
            print(f"[thirdparty] error: recipe not found: {name}", file=sys.stderr)
            failures += 1
            continue
        version = resolve_version(cls)
        package_id = compute_package_id(
            cls, recipes_root, name, version, args.build_type, args.target_os, args.target_arch)
        layout = _layout_dir(build_root, name, package_id, args.output)
        if not (layout / "index.json").exists():
            print(f"[thirdparty] error: no OCI image for {name} ({package_id}); "
                  f"run 'thirdparty oci build {name}' first", file=sys.stderr)
            failures += 1
            continue
        tag = args.tag or version
        client = OciRegistryClient(
            owner, name, registry=args.registry, prefix=args.prefix,
            username=args.username, password=args.password, log=lambda m: print(m))
        print(f"[thirdparty] pushing {name}/{version} -> "
              f"{args.registry}/{owner}/{args.prefix}/{name}:{tag}")
        try:
            client.push_layout(layout, tag, dry_run=args.dry_run)
        except RecipeException as exc:
            print(f"[thirdparty] error: {exc}", file=sys.stderr)
            failures += 1
    if failures:
        sys.exit(1)


def _combine(args: argparse.Namespace) -> None:
    recipes_root, _build_root = _project()
    owner = _require_owner(args)
    names = resolve_names(recipes_root, args.recipe)
    failures = 0
    for name in names:
        cls = try_load_recipe_class(recipes_root, name)
        if cls is None:
            print(f"[thirdparty] error: recipe not found: {name}", file=sys.stderr)
            failures += 1
            continue
        tag = args.tag or resolve_version(cls)
        client = OciRegistryClient(
            owner, name, registry=args.registry, prefix=args.prefix,
            username=args.username, password=args.password, log=lambda m: print(m))
        print(f"[thirdparty] combining {args.registry}/{owner}/{args.prefix}/{name}:{tag} "
              "from per-platform tags")
        try:
            client.combine_index(tag, dry_run=args.dry_run)
        except RecipeException as exc:
            print(f"[thirdparty] error: {exc}", file=sys.stderr)
            failures += 1
    if failures:
        sys.exit(1)


def _require_owner(args: argparse.Namespace) -> str:
    owner = args.owner or os.environ.get("GITHUB_REPOSITORY_OWNER")
    if not owner and not args.dry_run:
        print("[thirdparty] error: --owner (or GITHUB_REPOSITORY_OWNER) is required",
              file=sys.stderr)
        sys.exit(1)
    return owner or "o3de"  # dry-run placeholder so the planned repo path is illustrative
