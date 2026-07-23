import argparse
import sys
from pathlib import Path

from thirdparty._internal.cli._recipes import resolve_names
from thirdparty._internal.cli.command import command
from thirdparty._internal.graph import package_root
from thirdparty._internal.pack import ARCHIVE_DEFAULT_FORMAT, BACKENDS, gather_meta, get_backend
from thirdparty.errors import RecipeException


def setup_parser(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "recipe", metavar="<recipe>", nargs="*",
        help="Recipe name(s) or glob pattern(s) to archive (default: all built)")
    p.add_argument(
        "--format", default=ARCHIVE_DEFAULT_FORMAT, choices=sorted(BACKENDS), dest="fmt",
        metavar="<format>", help=f"Archive format (default: {ARCHIVE_DEFAULT_FORMAT})")
    p.add_argument(
        "--build-type", default="Release", choices=["Debug", "Release", "RelWithDebInfo"],
        dest="build_type", metavar="<type>")
    p.add_argument(
        "--target-os", default=None, dest="target_os", metavar="<os>",
        help="Target OS whose build to archive (default: build machine)")
    p.add_argument(
        "--target-arch", default=None, dest="target_arch", metavar="<arch>",
        help="Target architecture (X64 or ARM) whose build to archive (default: build machine)")
    p.add_argument(
        "--output", default=None, dest="output", metavar="<dir>",
        help="Output directory (default: build/<name>/<package_id>/dist)")


@command
def archive(args: argparse.Namespace) -> None:
    """Package a built recipe into a compressed archive (tar, tar.gz, tar.bz2, tar.xz, or zip)."""
    cwd = Path.cwd()
    recipes_root = cwd / "recipes"
    build_root = cwd / "build"
    if not recipes_root.exists():
        print(f"[thirdparty] error: no 'recipes/' directory in {cwd}", file=sys.stderr)
        sys.exit(1)

    names = resolve_names(recipes_root, args.recipe)
    backend = get_backend(args.fmt)
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
        out = Path(args.output) if args.output else package_root(
            build_root, name, meta.package_id) / "dist"
        produced = backend.pack(staged, out, meta)
        print(str(produced.resolve()))
    if failures:
        sys.exit(1)
