#!/usr/bin/env python3
"""Sort recipe license tuples alphabetically and remove redundant parentheses.

Only simple ``license = ...`` assignments whose tuple elements are all string
literals are changed.  Other assignments, such as ``self.license = ...`` or
computed license values, are left untouched.

Usage:
    python tools/fix_license_tuples.py              # dry-run, scan recipes/
    python tools/fix_license_tuples.py --fix        # apply fixes
    python tools/fix_license_tuples.py path/to/file.py [--fix]
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = (ROOT / "recipes",)


def _is_license_target(target: cst.BaseAssignTargetExpression) -> bool:
    return isinstance(target, cst.Name) and target.value == "license"


def _string_value(node: cst.BaseExpression) -> str | None:
    if not isinstance(node, cst.SimpleString):
        return None

    try:
        value = ast.literal_eval(node.value)
    except (SyntaxError, ValueError):
        return None

    return value if isinstance(value, str) else None


def _has_multiline_spacing(node: cst.Tuple) -> bool:
    for element in node.elements:
        comma = element.comma
        if isinstance(comma, cst.Comma) and isinstance(
            comma.whitespace_after, cst.ParenthesizedWhitespace
        ):
            return True
    return False


def _comma_for(elements: tuple[cst.Element, ...]) -> cst.Comma:
    for element in elements:
        if isinstance(element.comma, cst.Comma):
            return cst.Comma(
                whitespace_before=element.comma.whitespace_before,
                whitespace_after=element.comma.whitespace_after,
            )
    return cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))


def _sort_tuple(node: cst.Tuple) -> cst.Tuple | None:
    if len(node.elements) < 2:
        return None

    keyed_elements: list[tuple[str, cst.Element]] = []
    for element in node.elements:
        value = _string_value(element.value)
        if value is None:
            return None
        keyed_elements.append((value, element))

    sorted_elements = sorted(keyed_elements, key=lambda item: item[0])
    is_ordered = [value for value, _ in keyed_elements] == [
        value for value, _ in sorted_elements
    ]
    has_redundant_parens = (
        bool(node.lpar) and bool(node.rpar) and not _has_multiline_spacing(node)
    )

    if is_ordered and not has_redundant_parens:
        return None

    comma = _comma_for(node.elements)
    new_elements = []
    for index, (_, element) in enumerate(sorted_elements):
        element_comma: cst.Comma | cst.MaybeSentinel = comma
        if index == len(sorted_elements) - 1:
            element_comma = cst.MaybeSentinel.DEFAULT
        new_elements.append(element.with_changes(comma=element_comma))

    return node.with_changes(
        elements=tuple(new_elements),
        lpar=() if has_redundant_parens else node.lpar,
        rpar=() if has_redundant_parens else node.rpar,
    )


class _LicenseTupleFixer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, fix: bool) -> None:
        self.fix = fix
        self.findings: list[tuple[int, str, str]] = []  # (line, before, after)

    def leave_Assign(
        self, original_node: cst.Assign, updated_node: cst.Assign
    ) -> cst.Assign:
        if len(updated_node.targets) != 1 or not _is_license_target(
            updated_node.targets[0].target
        ):
            return updated_node

        if not isinstance(updated_node.value, cst.Tuple):
            return updated_node

        sorted_tuple = _sort_tuple(updated_node.value)
        if sorted_tuple is None:
            return updated_node

        pos = self.get_metadata(PositionProvider, original_node)
        self.findings.append(
            (
                pos.start.line,
                cst.Module([]).code_for_node(updated_node.value),
                cst.Module([]).code_for_node(sorted_tuple),
            )
        )

        if not self.fix:
            return updated_node

        return updated_node.with_changes(value=sorted_tuple)


def process_file(path: Path, fix: bool) -> list[tuple[int, str, str]]:
    source = path.read_text(encoding="utf-8")
    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        print(f"  SKIP (parse error): {exc}", file=sys.stderr)
        return []

    wrapper = MetadataWrapper(module)
    transformer = _LicenseTupleFixer(fix=fix)
    new_module = wrapper.visit(transformer)

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
        help="Apply license tuple cleanup instead of just reporting",
    )
    args = parser.parse_args()

    targets = collect_py_files(args.paths or list(DEFAULT_ROOTS))
    if not targets:
        print("No Python files found.")
        return 0

    total = 0
    affected = 0

    for path in targets:
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        findings = process_file(path, fix=args.fix)
        if findings:
            affected += 1
            total += len(findings)
            for line_no, before, after in findings:
                action = "fixed" if args.fix else "found"
                print(f"{rel}:{line_no}: {action} license tuple {before} -> {after}")

    if total == 0:
        print("No license tuples found that need cleanup.")
        return 0

    suffix = "cleaned up" if args.fix else "can be cleaned up (dry run - pass --fix to apply)"
    print(f"\n{total} license tuple(s) across {affected} file(s) {suffix}.")
    return 0 if args.fix else 1


if __name__ == "__main__":
    sys.exit(main())
