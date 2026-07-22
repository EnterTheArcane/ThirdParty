"""
Adds an idempotency sentinel to every _patch_sources() method that is called
from build() and contains replace_in_file() calls.

The sentinel pattern:
  - At start of _patch_sources: check for .patched file, return early if present
  - At end of _patch_sources: write the .patched sentinel file

The sentinel lives in self.source_folder, so it is cleared automatically
whenever the build directory is deleted (clean rebuild).
"""
import ast
import re
import sys
from pathlib import Path

RECIPES_DIR = Path(__file__).parent.parent / "recipes"

SENTINEL_LINES = [
    '        sentinel = os.path.join(self.source_folder, ".patched")\n',
    '        if os.path.exists(sentinel):\n',
    '            return\n',
]
SENTINEL_SAVE = '        save(self, sentinel, "")\n'


def find_method_line_range(lines: list[str], method_name: str) -> tuple[int, int] | None:
    """Return (start_line_idx, end_line_idx_exclusive) for the named method.
    Looks for '    def <method_name>(self)' at 4-space indent.
    The method ends when a new definition at indent ≤ 4 appears."""
    start = None
    for i, line in enumerate(lines):
        if re.match(r'    def ' + re.escape(method_name) + r'\b', line):
            start = i
            break
    if start is None:
        return None

    for i in range(start + 1, len(lines)):
        stripped = lines[i].rstrip('\n')
        if stripped == '':
            continue
        indent = len(stripped) - len(stripped.lstrip())
        if indent <= 4:
            return (start, i)

    return (start, len(lines))


def last_body_line_idx(lines: list[str], body_start: int, body_end: int) -> int:
    """Return the index of the last non-blank line in [body_start, body_end)."""
    idx = body_end - 1
    while idx >= body_start and lines[idx].rstrip('\n') == '':
        idx -= 1
    return idx


def has_import(content: str, symbol: str) -> bool:
    return bool(re.search(
        r'^from thirdparty\.tools\.files import[^\n]*\b' + re.escape(symbol) + r'\b',
        content, re.MULTILINE
    ))


def add_save_to_imports(lines: list[str]) -> list[str]:
    """Append ', save' to the thirdparty.tools.files import line."""
    for i, line in enumerate(lines):
        if re.match(r'from thirdparty\.tools\.files import', line) and 'save' not in line:
            lines[i] = line.rstrip('\n').rstrip() + ', save\n'
            break
    return lines


def process(filepath: Path) -> str:
    content = filepath.read_text(encoding='utf-8')
    lines = content.splitlines(keepends=True)

    if '.patched' in content:
        return 'skipped (already has sentinel)'

    range_ = find_method_line_range(lines, '_patch_sources')
    if range_ is None:
        return 'skipped (no _patch_sources)'

    start, end = range_

    # Determine body start (line after def, skipping optional docstring)
    body_start = start + 1
    if body_start < end:
        stripped = lines[body_start].strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            if stripped.count(quote) >= 2:
                body_start += 1
            else:
                body_start += 1
                while body_start < end and quote not in lines[body_start]:
                    body_start += 1
                body_start += 1

    # Insert sentinel check at body_start
    for offset, sline in enumerate(SENTINEL_LINES):
        lines.insert(body_start + offset, sline)

    # Adjust end index for the inserted lines
    end += len(SENTINEL_LINES)

    # Find last body line and insert save before the closing blank lines
    last = last_body_line_idx(lines, body_start, end)
    lines.insert(last + 1, SENTINEL_SAVE)

    # Add save to imports if needed
    if not has_import(''.join(lines), 'save'):
        lines = add_save_to_imports(lines)

    filepath.write_text(''.join(lines), encoding='utf-8')
    return 'updated'


TARGETS = [
    'assimp', 'autoconf', 'automake', 'clipper2', 'cpuinfo', 'dav1d',
    'glib', 'highway', 'icu', 'kuba-zip', 'libcurl', 'libde265',
    'libjpeg-turbo', 'libsamplerate', 'libtiff', 'libtool',
    'libvpx', 'x265', 'libxml2', 'openexr', 'openjpeg',
    'opensubdiv', 'physx', 'pkgconf', 'rvo2', 'spirv-tools',
    'tcl', 'wayland-protocols', 'wayland',
    # Already fixed manually:
    # 'pcre2', 'libjxl', 'freetype', 'ffmpeg', 'zstd',
]


def main():
    for name in TARGETS:
        fp = RECIPES_DIR / name / 'recipe.py'
        if not fp.exists():
            print(f'  NOT FOUND: {name}')
            continue
        result = process(fp)
        print(f'  {name}: {result}')


if __name__ == '__main__':
    main()
