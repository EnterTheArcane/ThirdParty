import fnmatch
import sys
from pathlib import Path


def resolve_names(recipes_root: Path, patterns: "list[str]") -> "list[str]":
    """Expand recipe name/glob *patterns* against ``recipes/`` (default: all recipes).

    Warns on a name that matches nothing; exits non-zero if nothing matched at all.  Shared by
    the ``oci`` and ``archive`` commands so their recipe selection behaves identically."""
    all_names = sorted(
        d.name for d in recipes_root.iterdir() if d.is_dir() and (d / "recipe.py").exists())
    if not patterns:
        return all_names
    names: list[str] = []
    for pat in patterns:
        if any(c in pat for c in "*?["):
            for m in fnmatch.filter(all_names, pat):
                if m not in names:
                    names.append(m)
        elif pat in all_names:
            if pat not in names:
                names.append(pat)
        else:
            print(f"[thirdparty] warn: no recipe named '{pat}'", file=sys.stderr)
    if not names:
        print("[thirdparty] no recipes matched", file=sys.stderr)
        sys.exit(1)
    return names
