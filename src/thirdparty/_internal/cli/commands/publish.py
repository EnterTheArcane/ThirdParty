import argparse
import os
import sys
from pathlib import Path

from thirdparty._internal.cli.command import command
from thirdparty._internal.cli.commands.package import _resolve_names
from thirdparty._internal.graph import package_root
from thirdparty._internal.pack import gather_meta
from thirdparty._internal.pack.ghcr import GHCRClient
from thirdparty._internal.pack.oci import OciBackend
from thirdparty.errors import RecipeException


def setup_parser(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "recipe", metavar="<recipe>", nargs="*",
        help="Recipe name(s) or glob pattern(s) to publish (default: all built)")
    p.add_argument(
        "--build-type", default="Release", choices=["Debug", "Release", "RelWithDebInfo"],
        dest="build_type", metavar="<type>")
    p.add_argument(
        "--target-os", default=None, dest="target_os", metavar="<os>",
        help="Target OS whose build to publish (default: build machine)")
    p.add_argument(
        "--target-arch", default=None, dest="target_arch", metavar="<arch>",
        help="Target architecture (X64 or ARM) whose build to publish (default: build machine)")
    p.add_argument("--registry", default="ghcr.io", help="Registry host (default: ghcr.io)")
    p.add_argument(
        "--owner", default=None,
        help="Registry owner/org (default: $GITHUB_REPOSITORY_OWNER)")
    p.add_argument(
        "--prefix", default="thirdparty", help="Repository prefix (default: thirdparty)")
    p.add_argument(
        "--tag", default=None, help="Image tag (default: the package version)")
    p.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Print the planned registry calls without pushing")


@command
def publish(args: argparse.Namespace) -> None:
    """Publish built packages to a container registry (GHCR) as OCI images."""
    cwd = Path.cwd()
    recipes_root = cwd / "recipes"
    build_root = cwd / "build"
    if not recipes_root.exists():
        print(f"[thirdparty] error: no 'recipes/' directory in {cwd}", file=sys.stderr)
        sys.exit(1)

    owner = args.owner or os.environ.get("GITHUB_REPOSITORY_OWNER")
    if not owner and not args.dry_run:
        print("[thirdparty] error: --owner (or GITHUB_REPOSITORY_OWNER) is required",
              file=sys.stderr)
        sys.exit(1)
    owner = owner or "o3de"  # dry-run placeholder so the planned repo path is illustrative

    names = _resolve_names(recipes_root, args.recipe)
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

        layout_dir = package_root(build_root, name, meta.package_id) / "dist" / "oci"
        if not (layout_dir / "index.json").exists():
            backend.pack(staged, layout_dir, meta)

        tag = args.tag or meta.version
        client = GHCRClient(
            owner, meta.name, registry=args.registry, prefix=args.prefix, log=lambda m: print(m))
        print(f"[thirdparty] publishing {meta.name}/{meta.version} "
              f"({meta.os}/{meta.arch}) -> {args.registry}/{owner}/{args.prefix}/{meta.name}:{tag}")
        try:
            client.push_layout(layout_dir, tag, dry_run=args.dry_run)
        except RecipeException as exc:
            print(f"[thirdparty] error: {exc}", file=sys.stderr)
            failures += 1

    if failures:
        sys.exit(1)
