#!/usr/bin/env python3
"""Detect (and optionally remove) blank lines immediately after class/def declarations.

Usage:
    python tools/fix_blank_lines.py              # dry-run, scan src/ and recipes/
    python tools/fix_blank_lines.py --fix        # apply fixes
    python tools/fix_blank_lines.py path/to/file.py [--fix]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = (ROOT / "src", ROOT / "recipes")


class _BlankLineAfterDeclTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, fix: bool) -> None:
        self.fix = fix
        # Each entry: (line_no, kind, name, blank_count)
        self.findings: list[tuple[int, str, str, int]] = []

    def _process(
        self,
        original_node: cst.CSTNode,
        updated_node: cst.CSTNode,
        kind: str,
        name: str,
    ) -> cst.CSTNode:
        body = updated_node.body  # type: ignore[attr-defined]
        if not isinstance(body, cst.IndentedBlock) or not body.body:
            return updated_node

        first_stmt = body.body[0]
        leading: tuple[cst.EmptyLine, ...] = getattr(first_stmt, "leading_lines", ())
        blank_lines = tuple(l for l in leading if l.comment is None)
        if not blank_lines:
            return updated_node

        pos = self.get_metadata(PositionProvider, original_node)
        self.findings.append((pos.start.line, kind, name, len(blank_lines)))

        if self.fix:
            kept = tuple(l for l in leading if l.comment is not None)
            new_first = first_stmt.with_changes(leading_lines=kept)
            new_body = body.with_changes(body=(new_first, *body.body[1:]))
            return updated_node.with_changes(body=new_body)  # type: ignore[return-value]

        return updated_node

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.CSTNode:
        return self._process(original_node, updated_node, "def", original_node.name.value)

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.CSTNode:
        return self._process(original_node, updated_node, "class", original_node.name.value)


def process_file(path: Path, fix: bool) -> list[tuple[int, str, str, int]]:
    source = path.read_text(encoding="utf-8")
    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        print(f"  SKIP (parse error): {exc}", file=sys.stderr)
        return []

    wrapper = MetadataWrapper(module)
    transformer = _BlankLineAfterDeclTransformer(fix=fix)
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", type=Path, help="Files or directories to scan (default: src/ recipes/ tools/)")
    parser.add_argument("--fix", action="store_true", help="Remove the blank lines instead of just reporting them")
    args = parser.parse_args()

    targets = collect_py_files(args.paths or list(DEFAULT_ROOTS))
    if not targets:
        print("No Python files found.")
        return 0

    total_findings = 0
    affected_files = 0

    for path in targets:
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        findings = process_file(path, fix=args.fix)
        if findings:
            affected_files += 1
            total_findings += len(findings)
            for line_no, kind, name, blank_count in findings:
                blanks = "blank line" if blank_count == 1 else f"{blank_count} blank lines"
                action = "fixed" if args.fix else "found"
                print(f"{rel}:{line_no}: {action} {blanks} after {kind} '{name}'")

    if total_findings == 0:
        print("No blank lines after declarations found.")
        return 0

    suffix = "fixed" if args.fix else "found (dry run - pass --fix to apply)"
    print(f"\n{total_findings} instance(s) across {affected_files} file(s) {suffix}.")
    return 0 if args.fix else 1


if __name__ == "__main__":
    sys.exit(main())
