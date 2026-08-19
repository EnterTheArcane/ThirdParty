"""Case-variant symlinks so Windows headers/libs resolve on case-sensitive filesystems.

Windows code references headers and libs with inconsistent casing (``<Windows.h>``,
``Ws2_32.lib``), which only Linux build machines trip over. Following xwin's approach,
symlinks are added for the lowercase/UPPERCASE/Capitalized spelling of every entry plus
the exact spellings referenced by ``#include``/``#pragma comment(lib)`` directives in the
headers themselves. No-op on case-insensitive filesystems (Windows/macOS).
"""

import os
import re
from pathlib import Path
from typing import Iterable

from thirdparty.recipe import RecipeBase


_INCLUDE_RE = re.compile(rb'#\s*include\s*[<"]([^">]+)[">]')
_PRAGMA_LIB_RE = re.compile(rb'#\s*pragma\s+comment\s*\(\s*lib\s*,\s*"([^"]+)"')

# Anything plausibly textual in an SDK include tree; binaries (.lib/.pdb/...) are skipped.
_HEADER_SUFFIXES = (".h", ".hpp", ".hxx", ".inl", ".idl", ".rh", ".ver", "")


def _is_case_sensitive(probe_dir: Path) -> bool:
    """True when *probe_dir* lives on a case-sensitive filesystem."""
    probe = probe_dir / ".CaseProbe.tmp"
    try:
        probe.write_text("")
        try:
            return not (probe_dir / ".caseprobe.tmp").exists()
        finally:
            probe.unlink()
    except OSError:
        return False


class _DirIndex:
    """Per-directory map of lowercased name -> actual name, built lazily."""

    def __init__(self):
        self._cache: dict[str, dict[str, str]] = {}

    def lookup(self, directory: str, name: str) -> str | None:
        index = self._cache.get(directory)
        if index is None:
            try:
                index = {entry.lower(): entry for entry in os.listdir(directory)}
            except OSError:
                index = {}
            self._cache[directory] = index
        return index.get(name.lower())

    def add(self, directory: str, name: str):
        if directory in self._cache:
            self._cache[directory].setdefault(name.lower(), name)


def _symlink(directory: str, link_name: str, target_name: str, index: _DirIndex) -> bool:
    """Create ``directory/link_name -> target_name`` unless something is already there."""
    link_path = os.path.join(directory, link_name)
    if os.path.lexists(link_path):
        return False
    os.symlink(target_name, link_path)
    index.add(directory, link_name)
    return True


def _link_reference(roots: list[str], ref: str, index: _DirIndex) -> int:
    """Resolve *ref* case-insensitively under each root, symlinking mismatched segments."""
    created = 0
    segments = [s for s in re.split(r"[/\\]", ref) if s and s != "."]
    if not segments:
        return 0
    for root in roots:
        directory = root
        for segment in segments:
            actual = index.lookup(directory, segment)
            if actual is None:
                break
            if actual != segment and _symlink(directory, segment, actual, index):
                created += 1
            directory = os.path.join(directory, segment)
    return created


def _scan_references(include_dirs: list[str]) -> tuple[set[str], set[str]]:
    """Collect the paths referenced by #include and #pragma comment(lib) directives."""
    includes: set[str] = set()
    libs: set[str] = set()
    for root in include_dirs:
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                if Path(filename).suffix.lower() not in _HEADER_SUFFIXES:
                    continue
                try:
                    content = Path(dirpath, filename).read_bytes()
                except OSError:
                    continue
                for match in _INCLUDE_RE.finditer(content):
                    try:
                        includes.add(match.group(1).decode("ascii").strip())
                    except UnicodeDecodeError:
                        continue
                for match in _PRAGMA_LIB_RE.finditer(content):
                    try:
                        libs.add(match.group(1).decode("ascii").strip())
                    except UnicodeDecodeError:
                        continue
    return includes, libs


def _spelling_variant_links(roots: list[str], index: _DirIndex) -> int:
    """Add lowercase/UPPERCASE/Capitalized symlinks next to every file and directory."""
    created = 0
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            for name in dirnames + filenames:
                for variant in (name.lower(), name.upper(), name.capitalize()):
                    if variant != name and index.lookup(dirpath, variant) == name:
                        if _symlink(dirpath, variant, name, index):
                            created += 1
    return created


def add_case_variant_symlinks(
    recipe: RecipeBase,
    include_dirs: Iterable[str | os.PathLike[str]],
    lib_dirs: Iterable[str | os.PathLike[str]] = ()) -> int:
    """Add case-variant symlinks to packaged Windows include/lib trees; returns the count.

    Call from ``package()`` with the include/lib folders as the consumer sees them.
    """
    include_roots = [os.fspath(d) for d in include_dirs if os.path.isdir(d)]
    lib_roots = [os.fspath(d) for d in lib_dirs if os.path.isdir(d)]
    all_roots = include_roots + lib_roots
    if not all_roots or not _is_case_sensitive(Path(all_roots[0])):
        return 0

    index = _DirIndex()
    created = _spelling_variant_links(all_roots, index)

    include_refs, lib_refs = _scan_references(include_roots)
    for ref in include_refs:
        created += _link_reference(include_roots, ref, index)
    for ref in lib_refs:
        candidates = {ref} if "." in os.path.basename(ref) else {ref, ref + ".lib"}
        for candidate in candidates:
            created += _link_reference(lib_roots, candidate, index)

    if created:
        recipe.output.info(f"Added {created} case-variant symlinks for case-sensitive filesystems")
    return created
