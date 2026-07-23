import argparse
import fnmatch
import sys
from pathlib import Path

from thirdparty._internal.cli.command import command
from thirdparty._internal.pack import DEFAULT_FORMAT, gather_meta, get_backend
from thirdparty.errors import RecipeException


def setup_parser(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "recipe", metavar="<recipe>", nargs="*",
        help="Recipe name(s) or glob pattern(s) to package (default: all built)")
    p.add_argument(
        "--format", default=DEFAULT_FORMAT, choices=["oci", "tar.gz", "zip"], dest="fmt",
        metavar="<format>", help="Package backend (default: oci)")
    p.add_argument(
        "--build-type", default="Release", choices=["Debug", "Release", "RelWithDebInfo"],
        dest="build_type", metavar="<type>")
    p.add_argument(
        "--target-os", default=None, dest="target_os", metavar="<os>",
        help="Target OS whose build to package (default: build machine)")
    p.add_argument(
        "--target-arch", default=None, dest="target_arch", metavar="<arch>",
        help="Target architecture (X64 or ARM) whose build to package (default: build machine)")
    p.add_argument(
        "--output", default=None, dest="output", metavar="<dir>",
        help="Output directory (default: build/<name>/<package_id>/dist)")
    p.add_argument(
        "--publish", action="store_true",
        help="After packaging (oci only), publish to a registry (see 'thirdparty publish')")
    p.add_argument(
        "--owner", default=None, help="Registry owner/org for --publish")
    p.add_argument(
        "--registry", default="ghcr.io", help="Registry host for --publish (default: ghcr.io)")
    p.add_argument(
        "--prefix", default="thirdparty", help="Repository prefix for --publish (default: thirdparty)")


@command
def package(args: argparse.Namespace) -> None:
    """Turn built/staged packages into distributable artifacts (OCI image, tar.gz, or zip)."""
    cwd = Path.cwd()
    recipes_root = cwd / "recipes"
    build_root = cwd / "build"
    if not recipes_root.exists():
        print(f"[thirdparty] error: no 'recipes/' directory in {cwd}", file=sys.stderr)
        sys.exit(1)

    names = _resolve_names(recipes_root, args.recipe)
    if args.publish and args.fmt != "oci":
        print("[thirdparty] error: --publish requires --format oci", file=sys.stderr)
        sys.exit(1)

    backend = get_backend(args.fmt)
    from thirdparty._internal.graph import package_root

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

        default_out = package_root(build_root, name, meta.package_id) / "dist"
        out_base = Path(args.output) if args.output else default_out
        # OCI produces a directory layout; keep it in its own subfolder so multiple
        # formats can coexist under the same dist/ dir.
        out_target = (out_base / "oci") if args.fmt == "oci" else out_base
        produced = backend.pack(staged, out_target, meta)
        print(str(produced.resolve()))

        if args.publish:
            _publish(produced, meta, args)

    if failures:
        sys.exit(1)


def _resolve_names(recipes_root: Path, patterns: "list[str]") -> "list[str]":
    all_names = sorted(
        d.name for d in recipes_root.iterdir() if d.is_dir() and (d / "recipe.py").exists())
    if not patterns:
        return all_names
    names: list[str] = []
    for pat in patterns:
        if any(c in pat for c in "*?["):
            for m in fnmatch.filter(all_names, pat):
                if m not in names:
                    names.append(m)
        elif pat in all_names:
            if pat not in names:
                names.append(pat)
        else:
            print(f"[thirdparty] warn: no recipe named '{pat}'", file=sys.stderr)
    if not names:
        print("[thirdparty] no recipes matched", file=sys.stderr)
        sys.exit(1)
    return names


def _publish(layout_dir: Path, meta: object, args: argparse.Namespace) -> None:
    from thirdparty._internal.pack.meta import PackageMeta
    from thirdparty._internal.pack.ghcr import GHCRClient

    assert isinstance(meta, PackageMeta)
    owner = args.owner
    if not owner:
        import os
        owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    if not owner:
        print("[thirdparty] error: --owner (or GITHUB_REPOSITORY_OWNER) required to publish",
              file=sys.stderr)
        sys.exit(1)
    client = GHCRClient(
        owner, meta.name, registry=args.registry, prefix=args.prefix,
        log=lambda m: print(m))
    client.push_layout(layout_dir, meta.version)
