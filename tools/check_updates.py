#!/usr/bin/env python3
"""
check_updates.py - Scan ThirdParty recipes for available upstream updates.

Parses each recipe.py to extract the source URL, then queries the GitHub API
to find the latest release or tag and compares it against the recipe's current
version.

Usage:
    python tools/check_updates.py
    python tools/check_updates.py --outdated-only
    python tools/check_updates.py --recipe joltphysics
    python tools/check_updates.py --json > updates.json

Environment:
    GITHUB_TOKEN   Personal access token for higher GitHub API rate limits.
                   Unauthenticated requests are capped at 60/hr; authenticated
                   requests allow 5000/hr.  Most users will need this set when
                   checking the full recipe list.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from packaging.version import Version, InvalidVersion
    _HAS_PACKAGING = True
except ImportError:
    _HAS_PACKAGING = False

RECIPES_DIR = Path(__file__).parent.parent / "recipes"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RecipeInfo:
    name: str
    version: str   # value of the class-level ``version`` attribute
    url: str       # first url= argument found in source()
    path: Path


@dataclass
class UpdateResult:
    recipe: RecipeInfo
    current_tag: str       # tag string used in the URL
    latest_tag: str        # latest upstream tag (empty if unknown)
    status: str            # "outdated" | "up-to-date" | "skipped" | "unknown" | "error"
    notes: str = ""


# ---------------------------------------------------------------------------
# Recipe parsing (AST-based - no imports executed)
# ---------------------------------------------------------------------------

def _collect_module_strings(tree: ast.Module) -> dict[str, str]:
    """Return module-level ``name = "literal"`` bindings."""
    bindings: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    if isinstance(node.value.value, str):
                        bindings[target.id] = node.value.value
    return bindings


def _first_get_url(tree: ast.AST, string_vars: dict[str, str]) -> Optional[str]:
    """Return the first ``url=`` keyword in any ``get(...)`` call."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = (
            func.id if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute)
            else None
        )
        if func_name != "get":
            continue
        for kw in node.keywords:
            if kw.arg != "url":
                continue
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
            if isinstance(kw.value, ast.Name):
                return string_vars.get(kw.value.id)
            # f-string / complex expression - skip
    return None


def parse_recipe(path: Path) -> Optional[RecipeInfo]:
    """Parse a recipe.py and return a :class:`RecipeInfo`, or *None* on failure."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return None

    string_vars = _collect_module_strings(tree)

    name: Optional[str] = None
    version: Optional[str] = None

    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "Recipe"):
            continue
        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            for target in item.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "name" and isinstance(item.value, ast.Constant):
                    name = item.value.value
                elif target.id == "version" and isinstance(item.value, ast.Constant):
                    version = item.value.value

    if not name:
        return None

    url = _first_get_url(tree, string_vars) or ""
    return RecipeInfo(name=name, version=version or "", url=url, path=path)


# ---------------------------------------------------------------------------
# GitHub URL parsing
# ---------------------------------------------------------------------------

# Matches: github.com/{owner}/{repo}/archive/refs/tags/{tag}.{ext}
#          github.com/{owner}/{repo}/archive/{tag}.{ext}
_GH_ARCHIVE_RE = re.compile(
    r"https://github\.com/([^/]+)/([^/]+)/archive/(?:refs/tags/)?([^/]+?)(?:\.[a-z.]+)?$"
)

# Matches: github.com/{owner}/{repo}/releases/download/{tag}/{filename}
_GH_RELEASE_RE = re.compile(
    r"https://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/[^/]+"
)


def parse_github_url(url: str) -> Optional[tuple[str, str, str]]:
    """Return ``(owner, repo, tag)`` from a GitHub source URL, or *None*."""
    for pattern in (_GH_RELEASE_RE, _GH_ARCHIVE_RE):
        m = pattern.match(url)
        if m:
            return m.group(1), m.group(2), m.group(3)
    return None


def is_commit_hash_url(url: str) -> bool:
    """Return True if the URL references a specific commit hash instead of a tag."""
    return bool(re.search(r"/[0-9a-f]{40}[./]", url))


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def _gh_request(path: str, token: Optional[str]) -> Optional[object]:
    """Make a GET request to the GitHub API and return parsed JSON."""
    req = Request(f"https://api.github.com{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError(
                "GitHub API rate limit exceeded. Set the GITHUB_TOKEN environment "
                "variable to a personal access token to raise the limit."
            ) from exc
        return None
    except (URLError, OSError):
        return None


def _tag_prefix(tag: str) -> str:
    """Return the non-numeric prefix of a tag (e.g. 'vulkan-sdk-' from 'vulkan-sdk-1.4.0')."""
    m = re.match(r"^(.*?)(\d)", tag)
    return m.group(1) if m else ""


def get_latest_github_tag(
    owner: str, repo: str, current_tag: str, token: Optional[str]
) -> Optional[str]:
    """
    Return the latest tag/release for *owner/repo* in the same release family
    as *current_tag*.

    Strategy:
    1. Try ``/releases/latest``.  Accept it only if the returned tag belongs to
       the same release family (same non-numeric prefix) as *current_tag*.
    2. Fall back to the ``/tags`` endpoint (newest-first, up to 30 entries).
       When *current_tag* has a non-numeric prefix filter tags to that prefix
       so we don't confuse release families (e.g. ``vulkan-sdk-*`` vs
       ``MoltenVK-*`` in the same repo).
    3. If no prefix-matching tag is found, return the newest tag overall.
    """
    current_prefix = _tag_prefix(current_tag)

    # 1. Latest release - accept only if same release family
    data = _gh_request(f"/repos/{owner}/{repo}/releases/latest", token)
    if isinstance(data, dict) and "tag_name" in data:
        release_tag: str = data["tag_name"]
        release_prefix = _tag_prefix(release_tag)
        # Same family when both prefixes are equal, or when neither has a prefix
        if current_prefix == release_prefix:
            return release_tag

    # 2. Tags endpoint (newest first)
    data = _gh_request(f"/repos/{owner}/{repo}/tags?per_page=30", token)
    if not isinstance(data, list) or not data:
        return None

    tags: list[str] = [t["name"] for t in data if isinstance(t, dict) and "name" in t]
    if not tags:
        return None

    if current_prefix:
        matching = [t for t in tags if t.startswith(current_prefix)]
        if matching:
            return matching[0]

    return tags[0]


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------

_STRIP_PREFIXES = (
    "release-", "releases/", "openssl-", "lcms", "hidapi-", "libwebm-",
    "yaml-cpp-", "pcre2-", "R_",
)


def normalize_version(tag: str) -> str:
    """
    Strip vendor-specific tag prefixes and return a plain version string.

    Examples::

        "v3.0.1"              -> "3.0.1"
        "vulkan-sdk-1.4.313"  -> "vulkan-sdk-1.4.313"  (prefix kept - non-numeric start)
        "R_2_8_1"             -> "2.8.1"
        "release-78.2"        -> "78.2"
    """
    s = tag
    # Strip leading "v" (very common)
    if re.match(r"^v\d", s):
        s = s[1:]
        return s
    for p in _STRIP_PREFIXES:
        if s.lower().startswith(p.lower()):
            s = s[len(p):]
            break
    # Replace underscores with dots (handles R_2_8_1 style)
    s = re.sub(r"(?<=\d)_(?=\d)", ".", s)
    return s


def versions_equal(current_tag: str, latest_tag: str) -> bool:
    """Return True if *current_tag* and *latest_tag* represent the same version."""
    if current_tag == latest_tag:
        return True
    c = normalize_version(current_tag)
    l_ = normalize_version(latest_tag)
    if c == l_:
        return True
    if _HAS_PACKAGING:
        try:
            return Version(c) == Version(l_)
        except InvalidVersion:
            pass
    return False


def current_is_older(current_tag: str, latest_tag: str) -> bool:
    """Return True if *current_tag* is strictly older than *latest_tag*."""
    if versions_equal(current_tag, latest_tag):
        return False
    c = normalize_version(current_tag)
    l_ = normalize_version(latest_tag)
    if _HAS_PACKAGING:
        try:
            return Version(c) < Version(l_)
        except InvalidVersion:
            pass
    # Fallback: lexicographic (inaccurate but better than nothing)
    return c < l_


# ---------------------------------------------------------------------------
# Per-recipe update check
# ---------------------------------------------------------------------------

def check_recipe(recipe: RecipeInfo, token: Optional[str]) -> UpdateResult:
    if not recipe.url:
        return UpdateResult(recipe, "", "", "skipped", "no source URL")

    if is_commit_hash_url(recipe.url):
        return UpdateResult(recipe, recipe.version, "", "skipped", "pinned to commit hash - manual review required")

    gh = parse_github_url(recipe.url)
    if gh is None:
        return UpdateResult(recipe, recipe.version, "", "skipped", "non-GitHub source")

    owner, repo, current_tag = gh

    try:
        latest_tag = get_latest_github_tag(owner, repo, current_tag, token)
    except RuntimeError as exc:
        return UpdateResult(recipe, current_tag, "", "error", str(exc))

    if not latest_tag:
        return UpdateResult(recipe, current_tag, "", "unknown", "could not fetch upstream tags")

    if current_is_older(current_tag, latest_tag):
        status = "outdated"
    else:
        status = "up-to-date"

    return UpdateResult(recipe, current_tag, latest_tag, status)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_STATUS_LABEL = {
    "outdated":   "OUTDATED",
    "up-to-date": "ok",
    "skipped":    "skipped",
    "unknown":    "?",
    "error":      "ERROR",
}

# ANSI colour codes (disabled on Windows unless FORCE_COLOR is set or stdout is redirected)
def _use_color() -> bool:
    force = os.environ.get("FORCE_COLOR", "")
    if force:
        return True
    if sys.platform == "win32":
        return False
    return sys.stdout.isatty()


_RESET  = "\033[0m"
_RED    = "\033[31m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_GREY   = "\033[90m"


def _color(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}" if _use_color() else text


def _status_display(status: str) -> str:
    label = _STATUS_LABEL.get(status, status)
    if status == "outdated":
        return _color(label, _RED)
    if status == "up-to-date":
        return _color(label, _GREEN)
    return _color(label, _GREY)


def print_table(results: list[UpdateResult], outdated_only: bool) -> None:
    filtered = [r for r in results if not outdated_only or r.status == "outdated"]
    if not filtered:
        print("All checked recipes are up to date.")
        return

    col_name    = max(len(r.recipe.name)    for r in filtered)
    col_current = max(len(r.current_tag)    for r in filtered)
    col_latest  = max(len(r.latest_tag)     for r in filtered)
    col_name    = max(col_name, 7)
    col_current = max(col_current, 11)
    col_latest  = max(col_latest, 10)

    header = (
        f"{'Package':<{col_name}}  "
        f"{'Current tag':<{col_current}}  "
        f"{'Latest tag':<{col_latest}}  Status"
    )
    print()
    print(header)
    print("-" * (len(header) + 10))

    for r in filtered:
        note = f"  ({r.notes})" if r.notes else ""
        print(
            f"{r.recipe.name:<{col_name}}  "
            f"{r.current_tag:<{col_current}}  "
            f"{r.latest_tag:<{col_latest}}  "
            f"{_status_display(r.status)}{note}"
        )

    outdated_count = sum(1 for r in results if r.status == "outdated")
    checked_count  = sum(1 for r in results if r.status in ("outdated", "up-to-date"))
    print()
    print(f"Summary: {outdated_count} outdated / {checked_count} checked "
          f"({len(results) - checked_count} skipped/unknown)")


def print_json(results: list[UpdateResult], outdated_only: bool) -> None:
    output = []
    for r in results:
        if outdated_only and r.status != "outdated":
            continue
        output.append({
            "name":        r.recipe.name,
            "version":     r.recipe.version,
            "current_tag": r.current_tag,
            "latest_tag":  r.latest_tag,
            "status":      r.status,
            "notes":       r.notes,
        })
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check ThirdParty recipes for available upstream updates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true",
        help="Emit results as JSON instead of a human-readable table.",
    )
    parser.add_argument(
        "--outdated-only", action="store_true",
        help="Only display packages that have newer upstream versions.",
    )
    parser.add_argument(
        "--recipe", metavar="NAME", action="append", dest="recipes",
        help="Check only the named recipe (repeatable, e.g. --recipe fmt --recipe zlib).",
    )
    parser.add_argument(
        "--concurrent", type=int, default=8, metavar="N",
        help="Maximum number of concurrent GitHub API requests (default: 8).",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print(
            "Warning: GITHUB_TOKEN is not set.  GitHub API calls are limited to "
            "60 requests/hour for unauthenticated clients.\n"
            "  Set GITHUB_TOKEN to a personal access token to raise this to 5000/hr.\n",
            file=sys.stderr,
        )

    # Collect recipes
    recipes: list[RecipeInfo] = []
    for recipe_dir in sorted(RECIPES_DIR.iterdir()):
        recipe_file = recipe_dir / "recipe.py"
        if not recipe_file.exists():
            continue
        if args.recipes and recipe_dir.name not in args.recipes:
            continue
        info = parse_recipe(recipe_file)
        if info:
            recipes.append(info)
        else:
            print(f"Warning: could not parse {recipe_file.relative_to(RECIPES_DIR.parent)}", file=sys.stderr)

    if not recipes:
        print("No recipes found.", file=sys.stderr)
        return 1

    print(f"Checking {len(recipes)} recipe(s)…", file=sys.stderr)

    # Run checks concurrently (I/O-bound: GitHub API)
    results: list[UpdateResult] = [None] * len(recipes)  # type: ignore[list-item]
    lock_stderr = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _log(msg: str) -> None:
        lock_stderr.submit(print, msg, file=sys.stderr)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrent) as pool:
        future_to_idx = {pool.submit(check_recipe, r, token): i for i, r in enumerate(recipes)}
        done_count = 0
        for fut in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[fut]
            done_count += 1
            try:
                result = fut.result()
            except Exception as exc:  # pragma: no cover
                result = UpdateResult(recipes[idx], "", "", "error", str(exc))
            results[idx] = result
            _log(f"  [{done_count:>{len(str(len(recipes)))}}/{len(recipes)}] {result.recipe.name}: {result.status}")

    lock_stderr.shutdown(wait=True)

    # Sort: outdated first, then alphabetical
    results.sort(key=lambda r: (r.status != "outdated", r.recipe.name))

    if args.as_json:
        print_json(results, args.outdated_only)
    else:
        print_table(results, args.outdated_only)

    return 0


if __name__ == "__main__":
    sys.exit(main())
