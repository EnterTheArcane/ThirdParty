import argparse
import fnmatch
import re
import sys
from pathlib import Path

from thirdparty._internal.cli.command import command
from thirdparty._internal.graph import Graph


def setup_parser(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "recipe", metavar="<recipe>", nargs="*", help="Root recipe name(s) or glob pattern(s) (default: all)")
    p.add_argument(
        "--format", "-f", default="tree", choices=["tree", "dot", "mermaid"], dest="fmt", help="Output format (default: tree)", )
    p.add_argument(
        "--no-tools", action="store_false", dest="tools", help="Exclude requires_tool (build tools) from the graph")
    p.add_argument(
        "--build-type", default="Release", choices=["Debug", "Release", "RelWithDebInfo"], dest="build_type", metavar="<type>", )


@command
def graph(args: argparse.Namespace) -> None:
    """Print the dependency graph of recipes (tree, DOT, or mermaid)."""
    cwd = Path.cwd()
    recipes_root = cwd / "recipes"
    if not recipes_root.exists():
        print(f"[thirdparty] error: no 'recipes/' directory in {cwd}", file=sys.stderr)
        sys.exit(1)

    all_names = sorted(
        d.name for d in recipes_root.iterdir() if d.is_dir() and (d / "recipe.py").exists())

    patterns = args.recipe or ["*"]
    roots: list[str] = []
    for pat in patterns:
        if any(c in pat for c in "*?["):
            for m in fnmatch.filter(all_names, pat):
                if m not in roots:
                    roots.append(m)
        elif pat in all_names:
            if pat not in roots:
                roots.append(pat)
        else:
            print(f"[thirdparty] warn: no recipe named '{pat}'", file=sys.stderr)

    if not roots:
        print("[thirdparty] no recipes matched", file=sys.stderr)
        sys.exit(1)

    g = Graph.build(recipes_root, roots, args.build_type, transitive=True)

    if args.fmt == "tree":
        _print_tree(g, roots, args.tools)
    elif args.fmt == "dot":
        _print_dot(g, args.tools)
    else:
        _print_mermaid(g, args.tools)


def _deps_of(g: Graph, name: str, tools: bool) -> list[tuple[str, bool]]:
    """Return [(dep_name, is_tool)] for a node, host deps first."""
    node = g[name]
    result: list[tuple[str, bool]] = [(d, False) for d in node.host_deps]
    if tools:
        result += [(d, True) for d in node.tool_deps]
    return result


def _print_tree(g: Graph, roots: list[str], tools: bool) -> None:
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf" in enc:
        tee, last_, pipe = "├── ", "└── ", "│   "
    else:
        tee, last_, pipe = "|-- ", "`-- ", "|   "

    def label(name: str) -> str:
        node = g.nodes.get(name)
        return f"{name}/{node.version}" if node else name

    def walk(name: str, prefix: str, on_path: set[str]) -> None:
        deps = _deps_of(g, name, tools)
        for i, (dep, is_tool) in enumerate(deps):
            last = i == len(deps) - 1
            connector = last_ if last else tee
            suffix = " (tool)" if is_tool else ""
            if dep in on_path:
                print(f"{prefix}{connector}{label(dep)}{suffix} (cycle)")
                continue
            print(f"{prefix}{connector}{label(dep)}{suffix}")
            child_prefix = prefix + ("    " if last else pipe)
            walk(dep, child_prefix, on_path | {dep})

    for root in roots:
        print(label(root))
        walk(root, "", {root})
        print()


def _safe_id(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_]", "_", name)


def _print_dot(g: Graph, tools: bool) -> None:
    print("digraph deps {")
    print("  rankdir=LR;")
    print('  node [shape=box, fontname="monospace"];')
    for name in sorted(g.nodes):
        node = g.nodes[name]
        ver = "" if node.version == "?" else f"\\n{node.version}"
        print(f'  "{name}" [label="{name}{ver}"];')
    for name in sorted(g.nodes):
        for dep, is_tool in _deps_of(g, name, tools):
            style = " [style=dashed]" if is_tool else ""
            print(f'  "{name}" -> "{dep}"{style};')
    print("}")


def _print_mermaid(g: Graph, tools: bool) -> None:
    print("flowchart LR")
    for name in sorted(g.nodes):
        node = g.nodes[name]
        ver = "" if node.version == "?" else f"<br/>{node.version}"
        print(f'  {_safe_id(name)}["{name}{ver}"]')
    for name in sorted(g.nodes):
        for dep, is_tool in _deps_of(g, name, tools):
            arrow = "-.->|tool|" if is_tool else "-->"
            print(f"  {_safe_id(name)} {arrow} {_safe_id(dep)}")
