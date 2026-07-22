#!/usr/bin/env python3
"""Move the latest_version method to be the first method in Recipe classes.

It belongs after the class-level attributes (name, version, license, etc.)
and before configure, requirements, and other methods.

Usage:
    python tools/sort_latest_version.py          # dry-run
    python tools/sort_latest_version.py --fix    # apply changes
    python tools/sort_latest_version.py path/to/recipe.py [--fix]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import libcst as cst

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = (ROOT / "recipes",)


class _MoveLatestVersionTransformer(cst.CSTTransformer):
    def __init__(self, fix: bool) -> None:
        self.fix = fix
        self.findings: list[tuple[str, str]] = []  # (class_name, file hint)

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.CSTNode:
        if not isinstance(updated_node.body, cst.IndentedBlock):
            return updated_node

        stmts = list(updated_node.body.body)

        # Split: leading attribute lines, then methods
        split = 0
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, cst.FunctionDef):
                split = i
                break
        else:
            return updated_node  # no methods at all

        attrs = stmts[:split]
        methods = stmts[split:]

        # Find latest_version in the methods list
        lv_idx = next(
            (i for i, s in enumerate(methods) if isinstance(s, cst.FunctionDef) and s.name.value == "latest_version"),
            None,
        )

        if lv_idx is None or lv_idx == 0:
            return updated_node  # not found or already first

        self.findings.append((updated_node.name.value, ""))

        if not self.fix:
            return updated_node

        lv = methods[lv_idx]
        # Give latest_version the same leading whitespace the first method had,
        # and give the first method back its own leading lines (unchanged).
        first_leading = methods[0].leading_lines  # type: ignore[attr-defined]
        lv = lv.with_changes(leading_lines=first_leading)

        new_methods = [lv] + [m for i, m in enumerate(methods) if i != lv_idx]
        new_body = updated_node.body.with_changes(body=(*attrs, *new_methods))
        return updated_node.with_changes(body=new_body)


def process_file(path: Path, fix: bool) -> list[tuple[str, str]]:
    source = path.read_text(encoding="utf-8")
    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        print(f"  SKIP (parse error): {exc}", file=sys.stderr)
        return []

    transformer = _MoveLatestVersionTransformer(fix=fix)
    new_module = module.visit(transformer)

    for i, (cls_name, _) in enumerate(transformer.findings):
        transformer.findings[i] = (cls_name, str(path))

    if fix and transformer.findings:
        path.write_text(new_module.code, encoding="utf-8")

    return transformer.findings


def collect_py_files(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    for p in paths:
        if p.is_file():
            result.append(p)
        elif p.is_dir():
            result.extend(sorted(p.rglob("*.py")))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to scan (default: recipes/)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply the reordering instead of just reporting",
    )
    args = parser.parse_args()

    targets = collect_py_files(args.paths or list(DEFAULT_ROOTS))
    if not targets:
        print("No Python files found.")
        return 0

    total = 0
    for path in targets:
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        findings = process_file(path, fix=args.fix)
        for cls_name, _ in findings:
            total += 1
            action = "moved" if args.fix else "needs move"
            print(f"{rel}: {action} latest_version in class '{cls_name}'")

    if total == 0:
        print("All latest_version methods are already in position.")
        return 0

    suffix = "reordered" if args.fix else "need reordering (dry run - pass --fix to apply)"
    print(f"\n{total} class(es) {suffix}.")
    return 0 if args.fix else 1


if __name__ == "__main__":
    sys.exit(main())
