import argparse
import sys
from pathlib import Path

from thirdparty._internal.cli.command import command
from thirdparty._internal.graph import package_root
from thirdparty._internal.loader import try_load_recipe_class, resolve_version, compute_package_id


def setup_parser(p: argparse.ArgumentParser) -> None:
    p.add_argument("package", metavar="<package>", help="Package name to provide")


@command
def provide(args: argparse.Namespace) -> None:
    name: str = args.package
    cwd = Path.cwd()
    recipes_root = cwd / "recipes"
    build_root = cwd / "build"

    cls = try_load_recipe_class(recipes_root, name)
    if cls is None:
        print(f"[thirdparty] error: recipe not found: {name}", file=sys.stderr)
        sys.exit(1)

    version = resolve_version(cls)
    pkg_path = package_root(build_root, name, compute_package_id(cls, recipes_root, name, version)) / "package"
    if not pkg_path.exists():
        print(f"[thirdparty] error: package not built: {name}/{version}", file=sys.stderr)
        sys.exit(1)

    print(str(pkg_path.resolve()))
