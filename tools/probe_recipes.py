#!/usr/bin/env python3
"""Probe all recipes: load them, resolve their dependencies, and print the dep graph.

Usage:  python tools/probe_recipes.py [--dot | --build-order]
  --dot          emit Graphviz DOT to stdout instead of text tree
  --build-order  print topological build order (leaf -> root)

Thin wrapper around the library's graph resolution (loader + graph.Graph.build).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sure the src/ tree is importable
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from thirdparty._internal.graph.graph import Graph


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dot", action="store_true", help="Emit Graphviz DOT")
    ap.add_argument("--build-order", action="store_true", help="Print topological build order")
    args = ap.parse_args()

    recipes_root = REPO / "recipes"
    names = sorted(d.name for d in recipes_root.iterdir()
                   if d.is_dir() and (d / "recipe.py").exists())

    g = Graph.build(recipes_root, names, "Release", transitive=True)
    known = set(g.names())
    # Direct host (library) dependencies, restricted to known local recipes.
    deps_of = {n: [d for d in g[n].host_deps if d in known] for n in g.names()}
    errors = [n for n in g.names() if g[n].recipe_cls is None]

    if args.dot:
        print("digraph deps {")
        print('  rankdir=LR; node [shape=box];')
        for name, deps in deps_of.items():
            for dep in deps:
                print(f'  "{name}" -> "{dep}";')
        print("}")
        return

    order = g.topo_order()

    if args.build_order:
        print("\n=== Build Order (leaf -> root) ===")
        for i, n in enumerate(order, 1):
            deps = deps_of.get(n, [])
            dep_str = f"  deps: {deps}" if deps else ""
            print(f"  {i:3d}. {n}{dep_str}")
        return

    # Default: print full dep tree
    print(f"\n=== Recipes ({len(names)}) ===")
    for n in order:
        deps = deps_of.get(n, [])
        dep_str = f" -> {deps}" if deps else ""
        print(f"  {n}{dep_str}")

    if errors:
        print(f"\n=== Load/Parse Errors ({len(errors)}) ===")
        for n in errors:
            print(f"  {n}")

    print(f"\nTotal: {len(names)} recipes, {len(errors)} errors")


if __name__ == "__main__":
    main()
