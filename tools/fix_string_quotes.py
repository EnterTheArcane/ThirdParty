#!/usr/bin/env python3
"""Convert single-quoted strings to double quotes throughout the codebase.

Strings that contain a literal double-quote character are left unchanged,
since converting them would require adding escape sequences.

Applies to regular strings, byte strings, raw strings, f-strings, and
triple-quoted variants of all the above.

Usage:
    python tools/fix_string_quotes.py              # dry-run, scan src/ and recipes/
    python tools/fix_string_quotes.py --fix        # apply fixes
    python tools/fix_string_quotes.py path/to/file.py [--fix]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = (ROOT / "src", ROOT / "recipes")


def _prefix_and_quote(raw: str) -> tuple[str, str, bool]:
    """Return (prefix, quote_char, is_triple) for a raw string literal."""
    i = 0
    while i < len(raw) and raw[i] not in ('"', "'"):
        i += 1
    prefix = raw[:i]
    quote_char = raw[i]
    is_triple = raw[i : i + 3] in ('"""', "'''")
    return prefix, quote_char, is_triple


def _is_raw(prefix: str) -> bool:
    return "r" in prefix.lower()


def _convert_simple(node: cst.SimpleString) -> cst.SimpleString | None:
    raw = node.value
    prefix, quote_char, is_triple = _prefix_and_quote(raw)

    if quote_char != "'":
        return None

    if is_triple:
        content = raw[len(prefix) + 3 : -3]
        if '"""' in content:
            return None
        new_raw = prefix + '"""' + content + '"""'
    else:
        content = raw[len(prefix) + 1 : -1]
        if '"' in content:
            return None
        if not _is_raw(prefix):
            content = content.replace("\\'", "'")
        new_raw = prefix + '"' + content + '"'

    return node.with_changes(value=new_raw)


def _convert_fstring(node: cst.FormattedString) -> cst.FormattedString | None:
    if '"' in node.start:
        return None

    is_triple = node.start.endswith("'''")

    for part in node.parts:
        if isinstance(part, cst.FormattedStringText):
            if is_triple and '"""' in part.value:
                return None
            if not is_triple and '"' in part.value:
                return None

    new_start = node.start.replace("'", '"')
    new_end = node.end.replace("'", '"')

    new_parts = []
    for part in node.parts:
        if isinstance(part, cst.FormattedStringText):
            new_parts.append(part.with_changes(value=part.value.replace("\\'", "'")))
        else:
            new_parts.append(part)

    return node.with_changes(start=new_start, end=new_end, parts=tuple(new_parts))


class _QuoteFixer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, fix: bool) -> None:
        self.fix = fix
        self.findings: list[tuple[int, str]] = []  # (line, snippet)

    def leave_SimpleString(
        self, original_node: cst.SimpleString, updated_node: cst.SimpleString
    ) -> cst.BaseExpression:
        converted = _convert_simple(updated_node)
        if converted is None:
            return updated_node
        pos = self.get_metadata(PositionProvider, original_node)
        self.findings.append((pos.start.line, updated_node.value[:40]))
        return converted if self.fix else updated_node

    def leave_FormattedString(
        self, original_node: cst.FormattedString, updated_node: cst.FormattedString
    ) -> cst.BaseExpression:
        converted = _convert_fstring(updated_node)
        if converted is None:
            return updated_node
        pos = self.get_metadata(PositionProvider, original_node)
        snippet = updated_node.start + "..." + updated_node.end
        self.findings.append((pos.start.line, snippet[:40]))
        return converted if self.fix else updated_node


def process_file(path: Path, fix: bool) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8")
    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        print(f"  SKIP (parse error): {exc}", file=sys.stderr)
        return []

    wrapper = MetadataWrapper(module)
    transformer = _QuoteFixer(fix=fix)
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
        help="Files or directories to scan (default: src/ recipes/)",
    )
    parser.add_argument(
        "--fix", action="store_true", help="Apply quote conversion instead of just reporting"
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
            for line_no, snippet in findings:
                action = "fixed" if args.fix else "found"
                print(f"{rel}:{line_no}: {action} {snippet}")

    if total == 0:
        print("No single-quoted strings found that can be converted.")
        return 0

    suffix = "converted" if args.fix else "can be converted (dry run - pass --fix to apply)"
    print(f"\n{total} string(s) across {affected} file(s) {suffix}.")
    return 0 if args.fix else 1


if __name__ == "__main__":
    sys.exit(main())
