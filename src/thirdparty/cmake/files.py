from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from thirdparty.recipe import RecipeBase

# cmake_minimum_required(VERSION <min>[...<max>] [FATAL_ERROR]) - case-insensitive.
_MIN_RE = re.compile(
    r"(?P<prefix>cmake_minimum_required\s*\(\s*VERSION\s+)"
    r"(?P<min>\d+(?:\.\d+)*)"
    r"(?P<range>(?:\s*\.\.\.?\s*\d+(?:\.\d+)*)?)"
    r"(?P<fatal>\s+FATAL_ERROR)?"
    r"(?P<close>\s*\))",
    re.IGNORECASE)


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def set_cmake_minimum_required(recipe: RecipeBase, version: str = "3.10", path: str | Path | None = None) -> None:
    """Raise a CMakeLists' ``cmake_minimum_required`` floor to at least *version*.

    Rewrites the first ``cmake_minimum_required(VERSION ...)`` call, preserving a trailing
    ``FATAL_ERROR`` and any ``...max`` range (dropping the range when *version* exceeds the
    old max, since ``min > max`` is invalid).  No-op when the declared minimum is already
    ``>= version``.  Lets recipes with an old upstream minimum build without the global
    ``CMAKE_POLICY_VERSION_MINIMUM`` override (CMake 4.x drops support for ``< 3.5``) and
    without CMake's "Compatibility with CMake < 3.10 will be removed" deprecation warning.

    ``path`` defaults to ``<source>/CMakeLists.txt``; pass an explicit path for sub-project CMakeLists.
    """
    cml = Path(path) if path is not None else recipe.folders.source / "CMakeLists.txt"
    text = cml.read_text(encoding="utf-8")
    target = _version_tuple(version)

    def _replace(match: "re.Match[str]") -> str:
        if _version_tuple(match.group("min")) >= target:
            return match.group(0)
        tail = ""
        max_match = re.search(r"(\d+(?:\.\d+)*)\s*$", match.group("range"))
        if max_match and _version_tuple(max_match.group(1)) >= target:
            tail = f"...{max_match.group(1)}"
        return f"{match.group('prefix')}{version}{tail}{match.group('fatal') or ''}{match.group('close')}"

    new_text, count = _MIN_RE.subn(_replace, text, count=1)
    if count and new_text != text:
        cml.write_text(new_text, encoding="utf-8")
        recipe.output.info(f"cmake_minimum_required raised to {version} in {cml.name}")
