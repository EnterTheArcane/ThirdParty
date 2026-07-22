#!/usr/bin/env python3
"""Reorder recipe methods into the canonical lifecycle order.

The main recipe lifecycle methods are emitted first, in this order:

    latest_version, configure, validate, requirements,
    package_id, source, generate, build, package, package_info

Any other methods (private helpers, properties, dunders) are kept *after* the
lifecycle methods, in their original relative order.  Class-level attributes
(name, version, license, ...) stay at the top, untouched.  libcst preserves the
exact formatting/comments of every node it moves.

Usage:
    python tools/order_recipe_methods.py              # dry-run, scan recipes/
    python tools/order_recipe_methods.py --apply      # rewrite files in place
    python tools/order_recipe_methods.py path/to/recipe.py [--apply]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import libcst as cst

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"

CANONICAL_ORDER = [
    "latest_version",
    "configure",
    "validate",
    "requirements",
    "package_id",
    "source",
    "generate",
    "build",
    "package",
    "package_info",
]
RANK = {name: i for i, name in enumerate(CANONICAL_ORDER)}


def _is_recipe_base(value: cst.BaseExpression) -> bool:
    # Matches ``RecipeBase`` and ``RecipeBase[...]``.
    if isinstance(value, cst.Subscript):
        value = value.value
    return isinstance(value, cst.Name) and value.value == "RecipeBase"


class _ReorderMethods(cst.CSTTransformer):
    def __init__(self) -> None:
        self.changed = False

    def leave_ClassDef(
        self, original: cst.ClassDef, updated: cst.ClassDef
    ) -> cst.ClassDef:
        if not any(_is_recipe_base(b.value) for b in updated.bases):
            return updated
        block = updated.body
        if not isinstance(block, cst.IndentedBlock):
            return updated

        body = list(block.body)
        funcs = [s for s in body if isinstance(s, cst.FunctionDef)]
        non_funcs = [s for s in body if not isinstance(s, cst.FunctionDef)]

        canonical = sorted(
            (f for f in funcs if f.name.value in RANK),
            key=lambda f: RANK[f.name.value],
        )
        others = [f for f in funcs if f.name.value not in RANK]
        new_funcs = canonical + others

        if [f.name.value for f in new_funcs] == [f.name.value for f in funcs]:
            return updated  # already in order

        self.changed = True
        # Class-level attributes stay first; lifecycle methods then helpers follow.
        new_body = tuple(non_funcs) + tuple(new_funcs)
        return updated.with_changes(body=block.with_changes(body=new_body))


def reorder_source(src: str) -> str | None:
    module = cst.parse_module(src)
    transformer = _ReorderMethods()
    new_module = module.visit(transformer)
    if not transformer.changed:
        return None
    return new_module.code


def iter_targets(args_paths: list[str]) -> list[Path]:
    if args_paths:
        return [Path(p) for p in args_paths]
    return sorted(RECIPES.glob("*/recipe.py"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="recipe.py files (default: all recipes)")
    parser.add_argument("--apply", action="store_true", help="rewrite files in place")
    args = parser.parse_args()

    changed: list[Path] = []
    for path in iter_targets(args.paths):
        src = path.read_text()
        new_src = reorder_source(src)
        if new_src is None:
            continue
        changed.append(path)
        if args.apply:
            path.write_text(new_src)

    verb = "Reordered" if args.apply else "Would reorder"
    for path in changed:
        print(f"{verb}: {path.relative_to(ROOT)}")
    print(f"{verb} {len(changed)} recipe(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
