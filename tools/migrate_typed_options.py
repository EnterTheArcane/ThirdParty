#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import keyword
from pathlib import Path
from typing import Any

import libcst as cst


REPO = Path(__file__).resolve().parent.parent


def _literal(value: Any) -> str:
    if isinstance(value, str):
        return repr(value)
    return repr(value)


def _is_identifier(name: str) -> bool:
    return name.isidentifier() and not keyword.iskeyword(name)


def _scalar_type(default: Any, has_default: bool) -> str:
    if has_default:
        if isinstance(default, bool):
            return "bool"
        if isinstance(default, int):
            return "int"
        if isinstance(default, float):
            return "float"
        if isinstance(default, str):
            return "str"
    return "Any"


def _type_expr(possible_values: list[Any], default: Any, has_default: bool) -> str:
    if len(possible_values) == 2 and set(possible_values) == {True, False}:
        return "bool"

    if not has_default:
        if all(isinstance(value, str) for value in possible_values):
            return "str"
        if all(isinstance(value, int) and not isinstance(value, bool) for value in possible_values):
            return "int"
        if all(isinstance(value, float) for value in possible_values):
            return "float"

    if possible_values == ["ANY"]:
        return _scalar_type(default, has_default)

    if possible_values == [None, "ANY"]:
        scalar = _scalar_type(default, has_default)
        if scalar == "Any":
            scalar = "str"
        return f"{scalar} | None"

    if "ANY" in possible_values:
        fixed_values = [value for value in possible_values if value != "ANY"]
        scalar = _scalar_type(default, has_default)
        if scalar == "Any":
            scalar = "str"
        return f"Literal[{', '.join(_literal(value) for value in fixed_values)}] | {scalar}"

    return f"Literal[{', '.join(_literal(value) for value in possible_values)}]"


def _uses_typing(type_expr: str) -> set[str]:
    result: set[str] = set()
    if "Any" in type_expr:
        result.add("Any")
    if "Literal" in type_expr:
        result.add("Literal")
    return result


def _load_recipe_options(path: Path) -> tuple[dict[str, list[Any]], dict[str, Any]]:
    options: dict[str, list[Any]] = {}
    defaults: dict[str, Any] = {}
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "Recipe":
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "options":
                    options = ast.literal_eval(stmt.value)
                elif target.id == "default_options":
                    defaults = ast.literal_eval(stmt.value)
    return dict(options), dict(defaults)


def _has_explicit_options(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "Recipe":
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "options":
                    return True
    return False


def _render_options_class(options: dict[str, list[Any]], defaults: dict[str, Any]) -> tuple[str, set[str]]:
    lines = ["class _Options(RecipeOptions):"]
    post_class_lines: list[str] = []
    typing_imports: set[str] = set()
    invalid_annotations: list[tuple[str, str]] = []
    invalid_defaults: dict[str, Any] = {}
    possible_overrides: dict[str, list[Any]] = {}

    for name, possible_values in options.items():
        has_default = name in defaults
        default = defaults.get(name)
        type_expr = _type_expr(possible_values, default, has_default)
        typing_imports.update(_uses_typing(type_expr))
        if not has_default and type_expr in {"str", "int", "float", "Any"} and possible_values != ["ANY"]:
            possible_overrides[name] = possible_values

        if _is_identifier(name):
            if has_default:
                lines.append(f"    {name}: {type_expr} = {_literal(default)}")
            else:
                lines.append(f"    {name}: {type_expr}")
        else:
            invalid_annotations.append((name, type_expr))
            if has_default:
                invalid_defaults[name] = default

    for name, type_expr in invalid_annotations:
        post_class_lines.append(f"_Options.__annotations__[{_literal(name)}] = {type_expr}")

    if invalid_defaults:
        default_items = ", ".join(
            f"{_literal(name)}: {_literal(value)}" for name, value in invalid_defaults.items())
        post_class_lines.append(f"_Options.__defaults__ = {{{default_items}}}")
    if possible_overrides:
        override_items = ", ".join(
            f"{_literal(name)}: {_literal(value)}" for name, value in possible_overrides.items())
        post_class_lines.append(f"_Options.__possible_values__ = {{{override_items}}}")

    if len(lines) == 1:
        lines.append("    pass")

    rendered = "\n".join(lines) + "\n"
    if post_class_lines:
        rendered += "\n" + "\n".join(post_class_lines) + "\n"
    return rendered, typing_imports


def _is_recipebase(value: cst.BaseExpression) -> bool:
    if isinstance(value, cst.Name):
        return value.value == "RecipeBase"
    if isinstance(value, cst.Subscript) and isinstance(value.value, cst.Name):
        return value.value.value == "RecipeBase"
    return False


def _recipebase_options_base() -> cst.Subscript:
    return cst.Subscript(
        value=cst.Name("RecipeBase"),
        slice=[cst.SubscriptElement(slice=cst.Index(value=cst.Name("_Options")))],
    )


def _assigns_recipe_options(stmt: cst.CSTNode) -> bool:
    if not isinstance(stmt, cst.SimpleStatementLine):
        return False
    for small_stmt in stmt.body:
        if not isinstance(small_stmt, cst.Assign):
            if (
                isinstance(small_stmt, cst.Expr)
                and isinstance(small_stmt.value, cst.Call)
                and isinstance(small_stmt.value.func, cst.Attribute)
                and isinstance(small_stmt.value.func.value, cst.Name)
                and small_stmt.value.func.value.value in {"options", "default_options"}
                and small_stmt.value.func.attr.value == "update"
            ):
                return True
            continue
        for target in small_stmt.targets:
            value = target.target
            if isinstance(value, cst.Name) and value.value in {"options", "default_options"}:
                return True
            if (
                isinstance(value, cst.Subscript)
                and isinstance(value.value, cst.Name)
                and value.value.value == "default_options"
            ):
                return True
    return False


class _TypedOptionsTransformer(cst.CSTTransformer):
    def __init__(self, options_nodes: tuple[cst.CSTNode, ...]):
        self._options_nodes = options_nodes
        self._inserted = False

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:
        if original_node.name.value != "Recipe":
            return updated_node

        bases = [
            base.with_changes(value=_recipebase_options_base()) if _is_recipebase(base.value) else base
            for base in updated_node.bases
        ]
        body = [
            stmt for stmt in updated_node.body.body
            if not _assigns_recipe_options(stmt)
        ]
        return updated_node.with_changes(
            bases=bases,
            body=updated_node.body.with_changes(body=body),
        )

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        body: list[cst.CSTNode] = []
        for stmt in updated_node.body:
            if isinstance(stmt, cst.ClassDef) and stmt.name.value == "Recipe" and not self._inserted:
                options_nodes = list(self._options_nodes)
                if options_nodes and isinstance(options_nodes[0], cst.ClassDef):
                    options_nodes[0] = options_nodes[0].with_changes(
                        leading_lines=(cst.EmptyLine(), cst.EmptyLine()))
                body.extend(options_nodes)
                self._inserted = True
            body.append(stmt)
        return updated_node.with_changes(body=body)


def _ensure_typing_import(code: str, names: set[str]) -> str:
    if not names:
        return code

    lines = code.splitlines()
    names = set(names)
    for index, line in enumerate(lines):
        if not line.startswith("from typing import "):
            continue
        existing = [name.strip() for name in line.removeprefix("from typing import ").split(",")]
        merged = sorted(set(existing) | names)
        lines[index] = f"from typing import {', '.join(merged)}"
        return "\n".join(lines) + "\n"

    insert_at = 0
    while insert_at < len(lines):
        line = lines[insert_at]
        if line.startswith("import ") or line.startswith("from "):
            insert_at += 1
            continue
        break
    lines.insert(insert_at, f"from typing import {', '.join(sorted(names))}")
    return "\n".join(lines) + "\n"


def _ensure_recipe_options_import(code: str) -> str:
    return code.replace(
        "from thirdparty import RecipeBase\n",
        "from thirdparty import RecipeBase, RecipeOptions\n",
    )


def migrate_recipe(path: Path, *, dry_run: bool = False) -> bool:
    if not _has_explicit_options(path):
        return False

    options, defaults = _load_recipe_options(path)
    options_code, typing_imports = _render_options_class(options, defaults)
    options_nodes = tuple(cst.parse_module(options_code).body)

    source = path.read_text()
    module = cst.parse_module(source)
    updated = module.visit(_TypedOptionsTransformer(options_nodes))
    code = _ensure_typing_import(updated.code, typing_imports)
    code = _ensure_recipe_options_import(code)

    if code == source:
        return False
    if not dry_run:
        path.write_text(code)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipes", nargs="*", help="Recipe names to migrate; defaults to all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    recipes_root = REPO / "recipes"
    if args.recipes:
        paths = [recipes_root / name / "recipe.py" for name in args.recipes]
    else:
        paths = sorted(recipes_root.glob("*/recipe.py"))

    changed = []
    for path in paths:
        if migrate_recipe(path, dry_run=args.dry_run):
            changed.append(path)

    action = "Would migrate" if args.dry_run else "Migrated"
    for path in changed:
        print(path.relative_to(REPO))
    print(f"{action} {len(changed)} recipes")


if __name__ == "__main__":
    main()
