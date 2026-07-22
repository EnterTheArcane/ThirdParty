#!/usr/bin/env python3
"""Fail on local legacy package-manager vocabulary outside approved upstream-import context."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (ROOT / "src", ROOT / "recipes", ROOT / "tools")
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".cmake",
    ".props",
    ".lua",
    ".bzl",
    ".json",
    ".patch",
}
_legacy_title = "Co" + "nan"
_legacy_lower = "co" + "nan"
_legacy_upper = "CO" + "NAN"
TOKEN_RE = re.compile(
    rf"\b(?:{_legacy_title}[A-Za-z_]*|{_legacy_lower}[A-Za-z_]*|{_legacy_upper}[A-Za-z_]*)\b"
)

APPROVED_FILES = {
    Path("tools/port_recipe.py"),
    Path("tools/port_data.py"),
    Path("tools/audit_missing_deps.py"),
}

def _is_generated_or_cache(path: Path) -> bool:
    parts = set(path.parts)
    return "__pycache__" in parts or ".venv" in parts or "thirdparty.egg-info" in parts


def _approved(path: Path, line: str) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return Path(rel) in APPROVED_FILES


def main() -> int:
    failures: list[str] = []
    for root in SCAN_ROOTS:
        for path in root.rglob("*"):
            if not path.is_file() or _is_generated_or_cache(path):
                continue
            rel = path.relative_to(ROOT)
            rel_text = rel.as_posix()
            if TOKEN_RE.search(rel_text) and Path(rel_text) not in APPROVED_FILES:
                failures.append(f"{rel}: legacy token in file path")
            if path.suffix not in TEXT_SUFFIXES:
                continue
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if TOKEN_RE.search(line) and not _approved(path, line):
                    failures.append(f"{rel}:{line_no}: {line.strip()}")

    if failures:
        print("Disallowed legacy package-manager vocabulary found:", file=sys.stderr)
        print("\n".join(failures[:200]), file=sys.stderr)
        if len(failures) > 200:
            print(f"... {len(failures) - 200} more", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
