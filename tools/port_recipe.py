#!/usr/bin/env python3
"""port_recipe.py - Convert a conan-center-index recipe to ThirdParty format.

Usage::

    python tools/port_recipe.py <name> [--overwrite] [--dry-run]
    python tools/port_recipe.py --all [--overwrite]

Reads::
    <cci_root>/recipes/<name>/all/recipe.py
    <cci_root>/recipes/<name>/all/recipe_data.yml

Writes::
    <thirdparty_root>/recipes/<name>/recipe.py
    <thirdparty_root>/recipes/<name>/patches/<files>  (if any)
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Union

try:
    import libcst as cst
except ImportError:
    print("ERROR: libcst is required.  pip install libcst", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required.  pip install PyYAML", file=sys.stderr)
    sys.exit(1)

try:
    from packaging.version import Version as PkgVersion, InvalidVersion
except ImportError:
    print("ERROR: packaging is required.  pip install packaging", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Import mapping  (conan module → thirdparty module, None = drop import)
# ---------------------------------------------------------------------------

_IMPORT_MAP: dict[str, str | None] = {
    "conan.tools.cmake":          "thirdparty.tools.cmake",
    "conan.tools.files":          "thirdparty.tools.files",
    "conan.tools.scm":            "thirdparty.tools.scm",
    "conan.tools.microsoft":      "thirdparty.tools.microsoft",
    "conan.tools.apple":          "thirdparty.tools.apple",
    "conan.tools.build":          "thirdparty.tools.build",
    "conan.tools.env":            "thirdparty.tools.env",
    "conan.tools.gnu":            "thirdparty.tools.gnu",
    "conan.tools.meson":          "thirdparty.tools.meson",
    "conan.errors":               None,   # RecipeInvalidConfiguration - validate() removed
    "conan.tools.system":         None,   # system package installation - not supported
    "conan.tools.cross_building": None,   # we don't cross-compile
    "conan.tools.layout":         None,   # cmake_layout/basic_layout - layout() removed
}

# Symbols to drop from a specific module's import list
_FILTER_SYMBOLS: dict[str, set[str]] = {
    "conan.tools.cmake": {"cmake_layout", "basic_layout"},
    "conan.tools.files": {"export_recipe_data_patches"},   # no-op; export_sources() removed
    "conan.tools.env":   set(),  # VirtualBuildEnv/VirtualRunEnv are re-exported from thirdparty.tools.env
}

# Class-level attribute assignments that carry only upstream metadata or have
# no meaning in this build system (settings/package_type are unused here)
_REMOVE_CLASS_ATTRS: frozenset[str] = frozenset({
    "url", "homepage", "topics", "description",
    "short_paths", "extension_properties",
    "settings", "package_type",
    "package_id_embed_mode", "package_id_semi_embed_mode",
    # no_copy_source: not read by the build runner
    "no_copy_source",
})

# Methods that don't apply in our build model
_REMOVE_METHODS: frozenset[str] = frozenset({
    "export_sources",       # no conan export stage
    "layout",               # driver owns folder layout
    "validate",             # no validation step
    "validate_build",
    "system_requirements",  # no system package management
    "package_id",           # no package cache
    "deploy",
})


# ===========================================================================
# CST Transformer
# ===========================================================================

class _ConanTransformer(cst.CSTTransformer):
    """One-pass CST rewriter for conan-center-index → ThirdParty recipes."""

    def __init__(self, version: str, url: str, sha256: str) -> None:
        super().__init__()
        self._version = version
        self._url = url
        self._sha256 = sha256
        self._class_stack: list[bool] = []
        self._version_injected = False

    @property
    def _in_conan_class(self) -> bool:
        return bool(self._class_stack) and self._class_stack[-1]

    # ------------------------------------------------------------------
    # Module-level and class-level simple statements
    # ------------------------------------------------------------------

    def leave_SimpleStatementLine(
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ) -> Union[cst.SimpleStatementLine, cst.RemovalSentinel, "cst.FlattenSentinel[cst.SimpleStatementLine]"]:

        for stmt in updated_node.body:

            # Drop `required_conan_version = ...` at module level
            if not self._in_conan_class and isinstance(stmt, cst.Assign):
                for tgt in stmt.targets:
                    if (
                        isinstance(tgt.target, cst.Name)
                        and tgt.target.value == "required_conan_version"
                    ):
                        return cst.RemovalSentinel.REMOVE

            if self._in_conan_class and isinstance(stmt, cst.Assign):
                for tgt in stmt.targets:
                    if not isinstance(tgt.target, cst.Name):
                        continue
                    attr = tgt.target.value

                    if attr in _REMOVE_CLASS_ATTRS:
                        return cst.RemovalSentinel.REMOVE

                    # Inject `version = "X.Y.Z"` after the `name = ...` line
                    if attr == "name" and not self._version_injected:
                        self._version_injected = True
                        ver_line = _make_version_line(self._version, updated_node)
                        return cst.FlattenSentinel([updated_node, ver_line])

            if self._in_conan_class and isinstance(stmt, cst.AnnAssign):
                if (
                    isinstance(stmt.target, cst.Name)
                    and stmt.target.value in _REMOVE_CLASS_ATTRS
                ):
                    return cst.RemovalSentinel.REMOVE

        return updated_node

    # ------------------------------------------------------------------
    # Import rewriting
    # ------------------------------------------------------------------

    def leave_ImportFrom(
        self,
        original_node: cst.ImportFrom,
        updated_node: cst.ImportFrom,
    ) -> Union[cst.ImportFrom, cst.RemovalSentinel]:
        if updated_node.module is None:
            return updated_node

        mod = _module_str(updated_node.module)

        # Not a conan import at all - leave completely alone
        if not mod.startswith("conan"):
            return updated_node

        # `from conan import RecipeBase` → `from thirdparty import RecipeBase as RecipeBase`
        if mod == "conan":
            if isinstance(updated_node.names, (list, tuple)):
                kept = []
                for alias in updated_node.names:
                    if isinstance(alias.name, cst.Name) and alias.name.value == "RecipeBase":
                        kept.append(
                            alias.with_changes(
                                name=cst.Name("RecipeBase"),
                                asname=cst.AsName(
                                    whitespace_before_as=cst.SimpleWhitespace(" "),
                                    whitespace_after_as=cst.SimpleWhitespace(" "),
                                    name=cst.Name("RecipeBase"),
                                ),
                            )
                        )
                if kept:
                    return updated_node.with_changes(
                        module=_str_to_module("thirdparty"),
                        names=_fix_commas(kept),
                    )
            return cst.RemovalSentinel.REMOVE

        # Unknown conan.* → drop
        if mod.startswith("conan.") and mod not in _IMPORT_MAP:
            return cst.RemovalSentinel.REMOVE

        mapped = _IMPORT_MAP.get(mod)
        if mapped is None:
            return cst.RemovalSentinel.REMOVE

        if isinstance(updated_node.names, (list, tuple)):
            drop = _FILTER_SYMBOLS.get(mod, set())
            kept = [
                a for a in updated_node.names
                if not (isinstance(a.name, cst.Name) and a.name.value in drop)
            ]
            if not kept:
                return cst.RemovalSentinel.REMOVE
            return updated_node.with_changes(
                module=_str_to_module(mapped),
                names=_fix_commas(kept),
            )

        return updated_node.with_changes(module=_str_to_module(mapped))

    # ------------------------------------------------------------------
    # Class rename  (XxxConan → Recipe)
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        is_conan = any(
            isinstance(arg.value, cst.Name) and arg.value.value == "RecipeBase"
            for arg in node.bases
        )
        self._class_stack.append(is_conan)
        return True

    def leave_ClassDef(
        self,
        original_node: cst.ClassDef,
        updated_node: cst.ClassDef,
    ) -> cst.ClassDef:
        is_conan = self._class_stack.pop() if self._class_stack else False
        if not is_conan:
            return updated_node

        body = updated_node.body
        if isinstance(body, cst.IndentedBlock) and not body.body:
            body = body.with_changes(body=[cst.SimpleStatementLine(body=[cst.Pass()])])

        return updated_node.with_changes(name=cst.Name("Recipe"), body=body)

    # ------------------------------------------------------------------
    # Method removal
    # ------------------------------------------------------------------

    def leave_FunctionDef(
        self,
        original_node: cst.FunctionDef,
        updated_node: cst.FunctionDef,
    ) -> Union[cst.FunctionDef, cst.RemovalSentinel]:
        if self._in_conan_class and original_node.name.value in _REMOVE_METHODS:
            return cst.RemovalSentinel.REMOVE
        return updated_node

    # ------------------------------------------------------------------
    # get(**self.recipe_data["sources"][self.version], ...) → inline
    # ------------------------------------------------------------------

    def leave_Call(
        self,
        original_node: cst.Call,
        updated_node: cst.Call,
    ) -> cst.Call:
        if not (isinstance(updated_node.func, cst.Name) and updated_node.func.value == "get"):
            return updated_node

        args = list(updated_node.args)
        unpack_idx = next(
            (i for i, a in enumerate(args) if a.star == "**" and _is_recipe_data_sources(a.value)),
            None,
        )
        if unpack_idx is None:
            return updated_node

        before = args[:unpack_idx]
        after  = args[unpack_idx + 1:]

        has_dest = any(
            isinstance(a.keyword, cst.Name) and a.keyword.value == "destination"
            for a in after
        )

        injected = [
            _kwarg("url",    cst.SimpleString(f'"{self._url}"')),
            _kwarg("sha256", cst.SimpleString(f'"{self._sha256}"')),
        ]
        if not has_dest:
            injected.append(
                _kwarg("destination", cst.Attribute(
                    value=cst.Name("self"),
                    attr=cst.Name("source_folder"),
                    dot=cst.Dot(),
                ))
            )

        new_args = before + injected + after
        return updated_node.with_changes(args=_fix_arg_commas(new_args))


# ===========================================================================
# Regex post-processing
# ===========================================================================

_DROP_LINE_RE: list[re.Pattern] = [
    re.compile(r"^\s*VirtualBuildEnv\s*\(.*?\)\.generate\s*\(\s*\)\s*$"),
    re.compile(r"^\s*VirtualRunEnv\s*\(.*?\)\.generate\s*\(\s*\)\s*$"),
    re.compile(r"^\s*PkgConfigDeps\s*\(.*?\)\.generate\s*\(\s*\)\s*$"),
    re.compile(r"^\s*AutotoolsDeps\s*\(.*?\)\.generate\s*\(\s*\)\s*$"),
    # Dead Conan v1 compat: MockInfoProperty subscript assignments
    re.compile(r"""\.names\[["'](cmake_find_package|cmake_find_package_multi|pkg_config)["']"""),
    re.compile(r"""\.filenames\[["'](cmake_find_package|cmake_find_package_multi)["']"""),
    re.compile(r"""\.build_modules\[["'](cmake_find_package|cmake_find_package_multi)["']"""),
    # Dead Conan v1 compat: env_info (MockInfoProperty)
    re.compile(r"\bself\.env_info\."),
    # Dead Conan v1 compat: standalone TODO comments about cmake_find_package* / conan v2
    re.compile(
        r"^\s*#\s*TODO:.*(?:conan v2|cmake_find_package|global scope|Remove for Conan)",
        re.IGNORECASE,
    ),
]

# Strip version specifiers from dependency declarations.  All packages must use
# the single version built in this repo; versioned requires are never resolved.
_STRIP_DEP_VERSION_RE = re.compile(
    r"""(self\.(?:requires?|tool_requires?)\s*\(\s*["'])([^/"']+)/[^"']*(["'])"""
)

# _settings_build property block: always equals self.settings in our build system
_SETTINGS_BUILD_BLOCK_RE = re.compile(
    r'(?:[ \t]*#[^\n]*Remove for Conan[^\n]*\n)?'
    r'([ \t]*)@property\n'
    r'\1[ \t]+def _settings_build\(self\):?\n'
    r'(?:\1[ \t]+#[^\n]*\n)?'
    r'\1[ \t]+return getattr\(self,\s*["\']settings_build["\'],\s*self\.settings\)\n?',
    re.MULTILINE,
)


def _apply_regex_transforms(code: str) -> str:
    # Remove _settings_build property blocks
    code = _SETTINGS_BUILD_BLOCK_RE.sub("", code)
    # Replace remaining _settings_build usages with self.settings
    code = re.sub(r'\bself\._settings_build\b', 'self.settings', code)
    # Drop dead lines
    lines = code.splitlines(keepends=True)
    out = [ln for ln in lines if not any(p.search(ln.rstrip()) for p in _DROP_LINE_RE)]
    code = "".join(out)
    code = _STRIP_DEP_VERSION_RE.sub(r"\1\2\3", code)
    code = re.sub(r"\n{3,}", "\n\n", code)
    return code.lstrip("\n")


# ===========================================================================
# recipe_data.yml helpers
# ===========================================================================

def _pick_version(sources: dict) -> str:
    def _key(v: str):
        try:
            return (1, PkgVersion(str(v)))
        except InvalidVersion:
            return (0, str(v))
    return max(sources.keys(), key=_key)


def _read_recipe_data(cci_dir: Path) -> dict:
    p = cci_dir / "recipe_data.yml"
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _get_source_info(recipe_data: dict, version: str) -> tuple[str, str]:
    entry = (recipe_data.get("sources") or {}).get(str(version)) or {}
    url = entry.get("url", "")
    if isinstance(url, list):
        url = url[0]
    sha256 = entry.get("sha256", "") or entry.get("sha1", "") or ""
    return str(url), str(sha256)


def _copy_patches(recipe_data: dict, version: str, cci_dir: Path, out_dir: Path) -> None:
    entries = (recipe_data.get("patches") or {}).get(str(version)) or []
    if not entries:
        return
    out_patches = out_dir / "patches"
    out_patches.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        src_rel = entry.get("patch_file", "")
        if not src_rel:
            continue
        src = cci_dir / src_rel
        if not src.exists():
            print(f"  [patch] WARNING: {src.name} not found - skipping")
            continue
        dst = out_patches / src.name
        shutil.copy2(src, dst)
        print(f"  [patch] {src.name}")


_SKIP_NAMES = {"recipe.py", "test_package", "patches", "__pycache__"}

def _copy_data_files(cci_dir: Path, out_dir: Path) -> None:
    """Copy auxiliary data files (recipe_data.yml, CMakeLists.txt, .conf, etc.) that
    recipes reference at runtime, but are not recipe.py or test/patch directories."""
    for item in cci_dir.iterdir():
        if item.name in _SKIP_NAMES or item.name.startswith("."):
            continue
        if item.is_file() and item.suffix not in {".py"}:
            dst = out_dir / item.name
            shutil.copy2(item, dst)
            print(f"  [data] {item.name}")


# ===========================================================================
# libcst helpers
# ===========================================================================

def _module_str(node: cst.BaseExpression) -> str:
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        return _module_str(node.value) + "." + node.attr.value
    return ""


def _str_to_module(s: str) -> cst.BaseExpression:
    parts = s.split(".")
    result: cst.BaseExpression = cst.Name(parts[0])
    for part in parts[1:]:
        result = cst.Attribute(value=result, attr=cst.Name(part), dot=cst.Dot())
    return result


def _fix_commas(aliases: list[cst.ImportAlias]) -> list[cst.ImportAlias]:
    if not aliases:
        return aliases
    out = list(aliases)
    for i in range(len(out) - 1):
        if out[i].comma is cst.MaybeSentinel.DEFAULT:
            out[i] = out[i].with_changes(
                comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
            )
    out[-1] = out[-1].with_changes(comma=cst.MaybeSentinel.DEFAULT)
    return out


def _make_version_line(version: str, template: cst.SimpleStatementLine) -> cst.SimpleStatementLine:
    """Build a `    version = "X.Y.Z"` statement matching the indentation of template."""
    return template.with_changes(
        body=[
            cst.Assign(
                targets=[cst.AssignTarget(target=cst.Name("version"))],
                value=cst.SimpleString(f'"{version}"'),
            )
        ],
        leading_lines=[],
    )


def _is_recipe_data_sources(node: cst.BaseExpression) -> bool:
    """Return True if node is self.recipe_data["sources"][self.version]."""
    if not isinstance(node, cst.Subscript):
        return False
    # Inner: self.recipe_data["sources"]
    inner = node.value
    if not isinstance(inner, cst.Subscript):
        return False
    if len(inner.slice) != 1:
        return False
    idx = inner.slice[0].slice
    if not isinstance(idx, cst.Index):
        return False
    val = idx.value
    if not isinstance(val, cst.SimpleString):
        return False
    try:
        key = val.evaluated_value
    except Exception:
        return False
    if key != "sources":
        return False
    if not isinstance(inner.value, cst.Attribute):
        return False
    attr = inner.value
    return (
        isinstance(attr.value, cst.Name)
        and attr.value.value == "self"
        and attr.attr.value == "recipe_data"
    )


def _kwarg(name: str, value: cst.BaseExpression) -> cst.Arg:
    return cst.Arg(
        keyword=cst.Name(name),
        value=value,
        equal=cst.AssignEqual(
            whitespace_before=cst.SimpleWhitespace(""),
            whitespace_after=cst.SimpleWhitespace(""),
        ),
    )


def _fix_arg_commas(args: list[cst.Arg]) -> list[cst.Arg]:
    if not args:
        return args
    out = list(args)
    for i in range(len(out) - 1):
        if out[i].comma is cst.MaybeSentinel.DEFAULT:
            out[i] = out[i].with_changes(
                comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
            )
    out[-1] = out[-1].with_changes(comma=cst.MaybeSentinel.DEFAULT)
    return out


# ===========================================================================
# Core porter
# ===========================================================================

def _find_cci_root() -> Path:
    candidates = [
        Path(r"D:\OpenSource\conan-center-index"),
        Path(__file__).resolve().parents[4] / "OpenSource" / "conan-center-index",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    raise RuntimeError("Cannot auto-detect CCI root - pass --cci-root")


def _find_cci_dir(cci_root: Path, name: str, subdir: str | None = None) -> Path | None:
    base = cci_root / "recipes" / name
    if not base.is_dir():
        return None
    if subdir:
        explicit = base / subdir
        if (explicit / "recipe.py").exists():
            return explicit
    all_dir = base / "all"
    if (all_dir / "recipe.py").exists():
        return all_dir
    # Pick the highest-sorted version subfolder (reverse alpha == latest)
    for child in sorted(base.iterdir(), reverse=True):
        if child.is_dir() and (child / "recipe.py").exists():
            return child
    return None


def port_recipe(
    name: str,
    cci_root: Path,
    out_root: Path,
    dry_run: bool = False,
    overwrite: bool = False,
    cci_subdir: str | None = None,
    cci_name: str | None = None,
) -> bool:
    cci_dir = _find_cci_dir(cci_root, cci_name or name, cci_subdir)
    if cci_dir is None:
        print(f"[port] SKIP {name} - not found in CCI")
        return False

    out_path = out_root / name / "recipe.py"
    if not overwrite and out_path.exists() and not dry_run:
        print(f"[port] SKIP {name} - exists (--overwrite to replace)")
        return False

    recipe_data = _read_recipe_data(cci_dir)
    sources   = recipe_data.get("sources") or {}

    if sources:
        version     = _pick_version(sources)
        url, sha256 = _get_source_info(recipe_data, version)
    else:
        version, url, sha256 = "0.0.0", "", ""
        print(f"[port] WARNING {name} - no sources in recipe_data.yml")

    source_code = (cci_dir / "recipe.py").read_text(encoding="utf-8")

    try:
        tree        = cst.parse_module(source_code)
        transformer = _ConanTransformer(version=version, url=url, sha256=sha256)
        transformed = tree.visit(transformer).code
    except cst.ParserSyntaxError as exc:
        print(f"[port] WARNING {name} - libcst parse error: {exc}; CST skipped")
        transformed = source_code

    transformed = _apply_regex_transforms(transformed)

    if dry_run:
        print(f"# === {name} / {version} ===")
        print(transformed)
        return True

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(transformed, encoding="utf-8")
    print(f"[port] {name}/{version}")
    _copy_patches(recipe_data, version, cci_dir, out_root / name)
    _copy_data_files(cci_dir, out_root / name)
    return True


# ===========================================================================
# CLI
# ===========================================================================

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Port conan-center-index recipes to ThirdParty format."
    )
    parser.add_argument("name", nargs="?", metavar="<name>", help="Single recipe name")
    parser.add_argument("--all",       action="store_true", help="Port all dirs under --out-root")
    parser.add_argument("--cci-root",  default=None, metavar="PATH")
    parser.add_argument("--out-root",  default=None, metavar="PATH")
    parser.add_argument("--cci-subdir", default=None, metavar="SUBDIR",
                        help="Force a specific CCI recipe subdir (e.g. 6.x.x)")
    parser.add_argument("--cci-name",   default=None, metavar="NAME",
                        help="CCI recipe name when it differs from the output name")
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--overwrite", action="store_true")

    args = parser.parse_args(argv)

    cci_root = Path(args.cci_root) if args.cci_root else _find_cci_root()
    out_root = (
        Path(args.out_root) if args.out_root
        else Path(__file__).resolve().parent.parent / "recipes"
    )

    if args.all:
        names = sorted(d.name for d in out_root.iterdir() if d.is_dir())
    elif args.name:
        names = [args.name]
    else:
        parser.error("Provide a recipe name or --all")

    ok = skipped = 0
    for name in names:
        cci_subdir = getattr(args, 'cci_subdir', None)
        cci_name   = getattr(args, 'cci_name',   None)
        if port_recipe(name, cci_root, out_root, args.dry_run, args.overwrite, cci_subdir, cci_name):
            ok += 1
        else:
            skipped += 1

    if len(names) > 1:
        print(f"\n[port] {ok} ported, {skipped} skipped")


if __name__ == "__main__":
    main()
