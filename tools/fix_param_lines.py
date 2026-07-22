#!/usr/bin/env python3
"""Detect (and optionally fix) function defs with 3+ params that are all on one line.

Each parameter should be placed on its own line when there are 3 or more:

    def foo(a, b, c):          →    def foo(
        ...                             a,
                                        b,
                                        c):
                                        ...

Usage:
    python tools/fix_param_lines.py              # dry-run, scan src/ and recipes/
    python tools/fix_param_lines.py --fix        # apply fixes
    python tools/fix_param_lines.py path/to/file.py [--fix]
    python tools/fix_param_lines.py --min 4     # change threshold (default: 3)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = (ROOT / "src", ROOT / "recipes")

_NEWLINE_INDENT = cst.ParenthesizedWhitespace(
    first_line=cst.TrailingWhitespace(
        whitespace=cst.SimpleWhitespace(""),
        comment=None,
        newline=cst.Newline(value=None),
    ),
    empty_lines=[],
    indent=True,
    last_line=cst.SimpleWhitespace("    "),
)

_COMMA_NL = cst.Comma(
    whitespace_before=cst.SimpleWhitespace(""),
    whitespace_after=_NEWLINE_INDENT,
)


def _param_count(p: cst.Parameters) -> int:
    return (
        len(p.posonly_params)
        + len(p.params)
        + (1 if isinstance(p.star_arg, cst.Param) else 0)
        + len(p.kwonly_params)
        + (1 if p.star_kwarg is not None else 0)
    )


def _is_single_line(node: cst.FunctionDef) -> bool:
    """True when the entire param list is on the same line as the def keyword."""
    if not isinstance(node.whitespace_before_params, cst.SimpleWhitespace):
        return False
    # Confirm no comma already carries a line-break (partially-reformatted sig)
    for seq in (node.params.posonly_params, node.params.params, node.params.kwonly_params):
        for param in seq:
            if isinstance(param.comma, cst.Comma) and isinstance(
                param.comma.whitespace_after, cst.ParenthesizedWhitespace
            ):
                return False
    for maybe_param in (node.params.star_arg, node.params.star_kwarg):
        if isinstance(maybe_param, (cst.Param, cst.ParamStar)) and isinstance(
            getattr(maybe_param, "comma", None), cst.Comma
        ):
            if isinstance(maybe_param.comma.whitespace_after, cst.ParenthesizedWhitespace):
                return False
    return True


def _multiline_params(params: cst.Parameters) -> cst.Parameters:
    """Return a new Parameters with each param on its own line."""

    def _is_last_group(group_has, *later_groups_have) -> bool:
        return group_has and not any(later_groups_have)

    has_posonly = bool(params.posonly_params)
    has_params = bool(params.params)
    has_star = isinstance(params.star_arg, (cst.Param, cst.ParamStar))
    has_kwonly = bool(params.kwonly_params)
    has_kwarg = params.star_kwarg is not None

    def set_commas(seq: tuple, is_last_group: bool) -> tuple:
        result = []
        for i, p in enumerate(seq):
            is_last = is_last_group and i == len(seq) - 1
            result.append(p.with_changes(comma=cst.MaybeSentinel.DEFAULT if is_last else _COMMA_NL))
        return tuple(result)

    new_posonly = set_commas(
        params.posonly_params,
        _is_last_group(has_posonly, has_params, has_star, has_kwonly, has_kwarg),
    )

    new_params = set_commas(
        params.params,
        _is_last_group(has_params, has_star, has_kwonly, has_kwarg),
    )

    new_star_arg = params.star_arg
    if isinstance(params.star_arg, cst.Param):
        is_last = _is_last_group(True, has_kwonly, has_kwarg)
        new_star_arg = params.star_arg.with_changes(
            comma=cst.MaybeSentinel.DEFAULT if is_last else _COMMA_NL
        )
    elif isinstance(params.star_arg, cst.ParamStar):
        new_star_arg = params.star_arg.with_changes(comma=_COMMA_NL)

    new_kwonly = set_commas(
        params.kwonly_params,
        _is_last_group(has_kwonly, has_kwarg),
    )

    new_star_kwarg = params.star_kwarg
    if params.star_kwarg is not None:
        new_star_kwarg = params.star_kwarg.with_changes(comma=cst.MaybeSentinel.DEFAULT)

    # posonly_ind (the `/`) also needs a newline comma when posonly_params are present
    new_posonly_ind = params.posonly_ind
    if isinstance(params.posonly_ind, cst.ParamSlash):
        is_last = _is_last_group(True, has_params, has_star, has_kwonly, has_kwarg)
        new_posonly_ind = params.posonly_ind.with_changes(
            comma=cst.MaybeSentinel.DEFAULT if is_last else _COMMA_NL
        )

    return params.with_changes(
        posonly_params=new_posonly,
        posonly_ind=new_posonly_ind,
        params=new_params,
        star_arg=new_star_arg,
        kwonly_params=new_kwonly,
        star_kwarg=new_star_kwarg,
    )


class _ParamLineFixer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, fix: bool, min_params: int) -> None:
        self.fix = fix
        self.min_params = min_params
        self.findings: list[tuple[int, str, int]] = []  # (line, name, count)

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.CSTNode:
        n = _param_count(updated_node.params)
        if n < self.min_params or not _is_single_line(updated_node):
            return updated_node

        pos = self.get_metadata(PositionProvider, original_node)
        self.findings.append((pos.start.line, updated_node.name.value, n))

        if not self.fix:
            return updated_node

        return updated_node.with_changes(
            params=_multiline_params(updated_node.params),
            whitespace_before_params=_NEWLINE_INDENT,
        )


def process_file(path: Path, fix: bool, min_params: int) -> list[tuple[int, str, int]]:
    source = path.read_text(encoding="utf-8")
    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        print(f"  SKIP (parse error): {exc}", file=sys.stderr)
        return []

    wrapper = MetadataWrapper(module)
    transformer = _ParamLineFixer(fix=fix, min_params=min_params)
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
        "--fix", action="store_true", help="Apply reformatting instead of just reporting"
    )
    parser.add_argument(
        "--min",
        type=int,
        default=4,
        metavar="N",
        dest="min_params",
        help="Minimum param count to trigger reformatting (default: 3)",
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
        findings = process_file(path, fix=args.fix, min_params=args.min_params)
        if findings:
            affected += 1
            total += len(findings)
            for line_no, name, n in findings:
                action = "fixed" if args.fix else "found"
                print(f"{rel}:{line_no}: {action} {n}-param def '{name}' on one line")

    if total == 0:
        print("No single-line multi-param defs found.")
        return 0

    suffix = "fixed" if args.fix else "need reformatting (dry run - pass --fix to apply)"
    print(f"\n{total} def(s) across {affected} file(s) {suffix}.")
    return 0 if args.fix else 1


if __name__ == "__main__":
    sys.exit(main())
