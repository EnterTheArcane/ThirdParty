import argparse
import fnmatch
import sys
from pathlib import Path

import colorama
from colorama import Fore, Style

from thirdparty._internal.cli.command import command
from thirdparty._internal.graph import Node, Graph, is_built
from thirdparty._internal.loader import make_probe_recipe, compute_package_id
from thirdparty.errors import RecipeInvalidConfiguration


def setup_parser(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "recipe", metavar="<recipe>", nargs="*", help="Recipe name(s) or glob pattern(s) to list (default: all)")
    p.add_argument(
        "--deps", action="store_true", help="Show each recipe's direct dependencies")
    p.add_argument(
        "--build-order", action="store_true", dest="build_order", help="List in dependency (build) order instead of alphabetically")
    p.add_argument(
        "--build-type", default="Release", choices=["Debug", "Release", "RelWithDebInfo"], dest="build_type", metavar="<type>", )


def _is_incompatible(recipes_root: Path, node: Node, build_type: str) -> bool:
    if node.recipe_cls is None:
        return False
    try:
        probe = make_probe_recipe(node.recipe_cls, recipes_root, node.name, node.version, build_type)
    except Exception:
        return False
    if hasattr(probe, "configure"):
        try:
            probe.configure()
        except Exception:
            pass
    if not hasattr(probe, "validate"):
        return False
    try:
        probe.validate()
    except RecipeInvalidConfiguration:
        return True
    except Exception:
        return False
    return False


@command(name="list")
def list_recipes(args: argparse.Namespace) -> None:
    """List available recipes with version and build status."""
    colorama.init()
    cwd = Path.cwd()
    recipes_root = cwd / "recipes"
    build_root = cwd / "build"
    if not recipes_root.exists():
        print(f"[thirdparty] error: no 'recipes/' directory in {cwd}", file=sys.stderr)
        sys.exit(1)

    all_names = sorted(
        d.name for d in recipes_root.iterdir() if d.is_dir() and (d / "recipe.py").exists())

    patterns = args.recipe or ["*"]
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

    graph = Graph.build(recipes_root, names, args.build_type)
    order = graph.topo_order() if args.build_order else sorted(names)

    rows: list[tuple[str, str, bool, bool, list[str], list[str]]] = []
    built_count = 0
    incompatible_count = 0
    for name in order:
        node = graph[name]
        incompatible = _is_incompatible(recipes_root, node, args.build_type)
        pkg_id = (compute_package_id(node.recipe_cls, recipes_root, name, node.version, args.build_type)
                  if node.recipe_cls and node.version != "?" else None)
        built = not incompatible and pkg_id is not None and is_built(build_root, name, node.version, pkg_id)
        built_count += built
        incompatible_count += incompatible
        rows.append((name, node.version, built, incompatible, node.host_deps, node.tool_deps))

    name_w = max(len("recipe"), max(len(r[0]) for r in rows))
    ver_w = max(len("version"), max(len(r[1]) for r in rows))
    print(f"{"recipe":<{name_w}}  {"version":<{ver_w}}  status")
    print(f"{"-" * name_w}  {"-" * ver_w}  ------")
    for name, version, built, incompatible, host_deps, tool_deps in rows:
        if incompatible:
            status = f"{Fore.YELLOW}incompatible{Style.RESET_ALL}"
        elif built:
            status = f"{Fore.GREEN}built{Style.RESET_ALL}"
        else:
            status = f"{Style.DIM}pending{Style.RESET_ALL}"
        print(f"{name:<{name_w}}  {version:<{ver_w}}  {status}")
        if args.deps:
            if host_deps:
                print(f"{"":<{name_w}}    requires: {", ".join(host_deps)}")
            if tool_deps:
                print(f"{"":<{name_w}}    tools:    {", ".join(tool_deps)}")

    print()
    pending_count = len(rows) - built_count - incompatible_count
    print(
        f"{len(rows)} recipes "
        f"({built_count} built, {incompatible_count} incompatible, {pending_count} pending)")
