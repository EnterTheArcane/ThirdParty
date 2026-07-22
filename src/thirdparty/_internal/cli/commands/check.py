import argparse
import fnmatch
import importlib
import pkgutil
import re
import sys
from pathlib import Path

import colorama
from colorama import Fore, Style

import thirdparty
from thirdparty._internal.cli.command import command
from thirdparty._internal.loader import _parse_recipe, make_probe_recipe, resolve_version
from thirdparty._internal.methods import run_configure_method
from thirdparty._internal.model.recipe import RecipeBase
from thirdparty.errors import RecipeInvalidConfiguration

# (os, arch) target matrix exercised by the recipes check.  These are the canonical INTERNAL
# names (settings.yml defines arch as just ARM/X64; OS names use Mac, not Macos) - tools that
# need the longer forms (x86_64, darwin, ...) map them at their own boundary.  The compiler is
# always detected from the build machine; only the target os/arch vary, which is what surfaces
# platform-specific configure()/requirements() bugs.
_PLATFORMS = [
    ("Android", "ARM"), ("Android", "X64"), ("iOS", "ARM"), ("Linux", "ARM"), ("Linux", "X64"), ("Mac", "ARM"), ("Mac", "X64"), ("Windows", "ARM"), ("Windows", "X64"),
]

_CLASS_RE = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


def setup_parser(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "recipe", metavar="<recipe>", nargs="*", help="Recipe name(s) or glob pattern(s) for the recipes check (default: all)")
    p.add_argument(
        "--build-type", default="Release", choices=["Debug", "Release", "RelWithDebInfo"], dest="build_type", metavar="<type>")
    p.add_argument(
        "--imports", action="store_true", help="Run only the imports check")
    p.add_argument(
        "--recipes", action="store_true", help="Run only the recipes (config) check")
    p.add_argument(
        "--duplicates", action="store_true", help="Run only the duplicate-class check")


def _check_imports() -> tuple[bool, int, list[tuple[str, str]]]:
    """Import every ``thirdparty.*`` submodule and collect any import-time errors.

    Catches the class of breakage ``compileall`` misses (missing/moved imports, circular
    imports, dropped re-exports) without needing to load a single recipe.
    """
    errors: list[tuple[str, str]] = []
    count = 0
    for module_info in pkgutil.walk_packages(thirdparty.__path__, "thirdparty."):
        count += 1
        try:
            importlib.import_module(module_info.name)
        except Exception as e:  # noqa: BLE001 - we want every failure, not just the first
            errors.append((module_info.name, f"{type(e).__name__}: {e}"))
    return not errors, count, errors


def _check_recipes(
    recipes_root: Path, names: list[str], build_type: str, ) -> tuple[bool, int, int, int, list[tuple[str, str, str]]]:
    """Load each recipe and drive configure/requirements on every target
    platform.  Returns (ok, n_recipes, n_configs_ok, n_skipped, failures)."""
    failures: list[tuple[str, str, str]] = []
    n_recipes = 0
    n_ok = 0
    n_skipped = 0
    for name in names:
        recipe_path = recipes_root / name / "recipe.py"
        if not recipe_path.exists():
            continue
        try:
            _module, cls = _parse_recipe(str(recipe_path))
        except Exception as e:  # noqa: BLE001
            failures.append((name, "load", f"{type(e).__name__}: {e}"))
            continue
        if not (isinstance(cls, type) and issubclass(cls, RecipeBase)):  # pyright: ignore[reportUnnecessaryIsInstance]  # defensive: _parse_recipe may return non-class objects
            continue
        n_recipes += 1
        version = resolve_version(cls)
        for target_os, target_arch in _PLATFORMS:
            try:
                probe = make_probe_recipe(
                    cls, recipes_root, name, version, build_type, target_os=target_os, target_arch=target_arch)
                run_configure_method(probe)
                n_ok += 1
            except RecipeInvalidConfiguration:
                n_skipped += 1
            except Exception as e:  # noqa: BLE001
                failures.append((name, f"{target_os}/{target_arch}", f"{type(e).__name__}: {e}"))
    return not failures, n_recipes, n_ok, n_skipped, failures


def _check_duplicates() -> tuple[bool, dict[str, list[str]]]:
    """Find class names defined in more than one file under the thirdparty package - the
    signature of an incomplete refactor (stale duplicate left behind)."""
    src_root = Path(thirdparty.__file__).parent
    seen: dict[str, list[str]] = {}
    for py in src_root.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for cls_name in _CLASS_RE.findall(text):
            seen.setdefault(cls_name, []).append(py.relative_to(src_root).as_posix())
    dups = {k: v for k, v in seen.items() if len(v) > 1}
    return not dups, dups


@command
def check(args: argparse.Namespace) -> None:
    """Validate framework imports, recipe configuration, and duplicate classes."""
    colorama.init()
    cwd = Path.cwd()
    recipes_root = cwd / "recipes"
    if not recipes_root.exists():
        print(f"[thirdparty] error: no 'recipes/' directory in {cwd}", file=sys.stderr)
        sys.exit(1)

    # If no check is explicitly selected, run them all.
    run_all = not (args.imports or args.recipes or args.duplicates)
    ok = True

    def header(text: str) -> None:
        print(f"{Style.BRIGHT}[thirdparty] check: {text}{Style.RESET_ALL}")

    def good(text: str) -> None:
        print(f"  {Fore.GREEN}OK{Style.RESET_ALL}  {text}")

    def bad(text: str) -> None:
        print(f"  {Fore.RED}FAIL{Style.RESET_ALL}  {text}")

    if run_all or args.imports:
        header("imports")
        imports_ok, n_modules, import_errors = _check_imports()
        if imports_ok:
            good(f"{n_modules} modules imported, 0 errors")
        else:
            ok = False
            bad(f"{len(import_errors)} import error(s) out of {n_modules} modules:")
            for module_name, err in import_errors:
                print(f"        {module_name} -> {err}")

    if run_all or args.recipes:
        all_names = sorted(
            d.name for d in recipes_root.iterdir() if d.is_dir() and (d / "recipe.py").exists())
        patterns = args.recipe or ["*"]
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

        header(f"recipes ({len(_PLATFORMS)} platforms)")
        recipes_ok, n_recipes, n_ok, n_skipped, failures = _check_recipes(
            recipes_root, names, args.build_type)
        summary = f"{n_recipes} recipes, {n_ok} configs ok, {n_skipped} skipped"
        if recipes_ok:
            good(summary)
        else:
            ok = False
            bad(f"{len(failures)} failure(s); {summary}:")
            for recipe_name, where, err in failures:
                print(f"        {recipe_name} [{where}] -> {err}")

    if run_all or args.duplicates:
        header("duplicate classes")
        dups_ok, dups = _check_duplicates()
        if dups_ok:
            good("no duplicate class definitions")
        else:
            ok = False
            bad(f"{len(dups)} class name(s) defined in multiple files:")
            for cls_name, files in sorted(dups.items()):
                print(f"        {cls_name}: {", ".join(files)}")

    print()
    if ok:
        print(f"[thirdparty] check: {Fore.GREEN}PASSED{Style.RESET_ALL}")
    else:
        print(f"[thirdparty] check: {Fore.RED}FAILED{Style.RESET_ALL}")
        sys.exit(1)
