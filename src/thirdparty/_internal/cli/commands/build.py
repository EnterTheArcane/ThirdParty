import argparse
import fnmatch
import os
import sys
import time
from collections import OrderedDict
from multiprocessing import cpu_count
from pathlib import Path

from thirdparty._internal.cli.command import command
from thirdparty._internal.cli import output as _out
from thirdparty._internal.graph import (
    Graph as _Graph, discover_requires as _get_requires, is_built as _is_built, COMPLETE_MARKER as _COMPLETE_MARKER,
    package_root as _package_root, invalidate_stale as _invalidate_stale, write_manifest as _write_manifest, )
from thirdparty._internal.loader import (
    make_probe_recipe, try_load_recipe_class as _try_load_recipe_class, resolve_version as _resolve_version, compute_package_id as _compute_package_id, resolve_package_id as _resolve_package_id, set_linux_compiler_executables as _set_linux_compiler_executables, set_linux_build_compiler_executables as _set_linux_build_compiler_executables, )
from thirdparty._internal.methods import run_configure_method as _run_configure_method
from thirdparty._internal.model.conf import Conf
from thirdparty._internal.model.dependencies import RecipeDependencies
from thirdparty._internal.model.info import Info
from thirdparty._internal.model.recipe import RecipeBase
from thirdparty._internal.model.refs import RecipeReference
from thirdparty._internal.model.requires import Requirement
from thirdparty._internal.model.state import RecipeState
from thirdparty._internal.util.detect import detect_settings, detect_platform_tag
from thirdparty._internal.util.files import rmdir as _rmdir
from thirdparty.env.environment import generate_aggregated_env
from thirdparty.errors import RecipeException


def _wipe(path: str | Path) -> None:
    """Remove a directory tree, clearing read-only attributes (e.g. Subversion `.svn` or
    msys2 source files on Windows) that make a plain ``shutil.rmtree`` fail.  ``rmdir``
    installs an onerror handler that chmods + retries; this swallows any final failure so
    cleanup stays best-effort (matching the old ``ignore_errors=True`` callers)."""
    try:
        _rmdir(str(path))
    except Exception:
        pass


def setup_parser(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "recipe", metavar="<recipe>", nargs="*", help="Recipe name(s) or glob pattern(s) to build (e.g. 'abseil' or '*'); omit to build all")
    p.add_argument(
        "--build-type", default="Release", choices=["Debug", "Release", "RelWithDebInfo"], dest="build_type", metavar="<type>", )
    p.add_argument(
        "--jobs", "-j", type=int, default=None, dest="jobs", metavar="<N>", help="Parallel build jobs (default: cpu count)", )
    p.add_argument(
        "--generate-only", action="store_true", dest="generate_only", help="Run only through generate() (no source download, build, or package)", )
    p.add_argument(
        "--resume", metavar="NAME", default=None, help="Skip all recipes before NAME in build order (multi-recipe builds)")
    p.add_argument(
        "--target-os", default=None, dest="target_os", metavar="<os>", help="Cross-compile target OS (e.g. Windows, Linux, Mac, Android, iOS, tvOS, visionOS); "
                                                                            "default: build machine")
    p.add_argument(
        "--target-arch", default=None, dest="target_arch", metavar="<arch>", help="Cross-compile target architecture (X64 or ARM); "
                                                                                  "default: build machine")
    p.add_argument(
        "--dry-run", action="store_true", help="Print build plan without building")
    p.add_argument(
        "--force", "--clean", action="store_true", dest="force", help="Rebuild even if already built (wipe source/build/package first)")
    p.add_argument(
        "--exact", action="store_true", help="Build ONLY the explicitly named recipe(s); their dependencies are "
                                             "still resolved so generators (CMakeDeps, etc.) can reference them, "
                                             "but no dependency is ever built, wiped, or otherwise modified")
    p.add_argument(
        "--fail-fast", action="store_true", dest="fail_fast", help="Stop after the first recipe failure")
    p.add_argument(
        "--verbose", "-v", action="store_true", dest="verbose", help="Verbose build output: show full compiler/build-tool "
                                                                     "command lines and compiler warnings (default: quiet - only "
                                                                     "the file being compiled and errors are logged)")


@command
def build(args: argparse.Namespace) -> None:
    """Build a recipe (and its dependencies) from source."""
    patterns: list[str] = args.recipe or ["*"]
    build_type: str = args.build_type
    generate_only: bool = getattr(args, "generate_only", False)
    force: bool = getattr(args, "force", False)
    verbose: bool = getattr(args, "verbose", False)
    resume: str | None = getattr(args, "resume", None)
    dry_run: bool = getattr(args, "dry_run", False)
    fail_fast: bool = getattr(args, "fail_fast", False)
    target_os: str | None = getattr(args, "target_os", None)
    target_arch: str | None = getattr(args, "target_arch", None)
    exact: bool = getattr(args, "exact", False)

    cwd = Path.cwd()
    recipes_root = cwd / "recipes"
    build_root = cwd / "build"

    if not recipes_root.exists():
        _out.error(f"no 'recipes/' directory in {cwd}")
        sys.exit(1)

    all_names = sorted(d.name for d in recipes_root.iterdir() if d.is_dir() and (d / "recipe.py").exists())
    all_names_set = set(all_names)
    names: list[str] = []
    is_multi = len(patterns) > 1 or any(c in pat for pat in patterns for c in ("*", "?", "["))
    for pat in patterns:
        if any(c in pat for c in ("*", "?", "[")):
            matched = fnmatch.filter(all_names, pat)
            if not matched:
                _out.warn(f"no recipes match '{pat}'")
            for m in matched:
                if m not in names:
                    names.append(m)
        else:
            if pat not in all_names_set:
                _out.error(f"recipe not found: {pat}")
                sys.exit(1)
            if pat not in names:
                names.append(pat)

    if not names:
        _out.error("no recipes matched")
        sys.exit(1)

    # --exact: the set of recipes the user explicitly asked for.  Only these are ever built;
    # everything else in the graph is resolved for reference but left untouched.
    exact_set: set[str] | None = set(names) if exact else None

    # Output folders are grouped by os+arch (the host/target platform) so that builds
    # for different platforms never collide.  --target-os/--target-arch select the target
    # (default: the build machine).  Tool deps (build context) always build for the build
    # machine; see _build_recipe / _build_dep_graph for the host-vs-build split.
    if is_multi or resume or dry_run:
        _build_ordered(
            recipes_root, build_root, names, build_type, jobs=args.jobs, resume=resume, dry_run=dry_run, force=force, generate_only=generate_only, fail_fast=fail_fast, target_os=target_os, target_arch=target_arch, exact_set=exact_set, verbose=verbose, )
    else:
        _build_recipe(
            recipes_root, build_root, names[0], build_type, set(), jobs=args.jobs, generate_only=generate_only, force=force, target_os=target_os, target_arch=target_arch, exact_set=exact_set, verbose=verbose)


def _load_recipe_class(recipes_root: Path, name: str) -> type[RecipeBase]:
    cls = _try_load_recipe_class(recipes_root, name)
    if cls is None:
        recipe_path = recipes_root / name / "recipe.py"
        if not recipe_path.exists():
            _out.error(f"recipe not found: {recipe_path}")
        else:
            _out.error(
                f"{recipe_path} must define a class named 'Recipe' "
                "that subclasses RecipeBase")
        sys.exit(1)
    return cls


def _instantiate(
    recipe_cls: type[RecipeBase], recipes_root: Path, build_root: Path, name: str, version: str, build_type: str, target_os: str | None, target_arch: str | None, jobs: int | None = None, verbose: bool = False, ) -> RecipeBase:
    recipe = make_probe_recipe(
        recipe_cls, recipes_root, name, version, build_type, jobs=jobs, target_os=target_os, target_arch=target_arch, verbose=verbose)

    pkg_root = _package_root(build_root, name, _resolve_package_id(recipe))
    source_dir = str(pkg_root / "source")
    build_dir = str(pkg_root / "build")
    pkg_dir = str(pkg_root / "package")
    gen_dir = build_dir

    recipe.folders.set_base_source(source_dir)
    recipe.folders.set_base_build(build_dir)
    recipe.folders.set_base_package(pkg_dir)
    recipe.folders.set_base_generators(gen_dir)

    return recipe


def _build_dep_graph(
    recipes_root: Path,
    build_root: Path,
    dep_names: list[str],
    build_type: str,
    target_os: str | None,
    target_arch: str | None,
    jobs: int | None = None,
    verbose: bool = False,
    tool_names: list[str] | None = None,
    _recipe_cache: dict[tuple[str, str | None, str | None, bool], tuple[Requirement, RecipeBase]] | None = None, ) -> RecipeDependencies:
    """Create a RecipeDependencies from a list of already-built packages.

    dep_names  - host (non-build) deps (build=False); inherit the parent's effective
                 target platform (``target_os``/``target_arch``).
    tool_names - requires_tool (build=True); built for the BUILD MACHINE (target reset).

    _recipe_cache is a shared dict[(dep_name, os, arch, is_build) → (Requirement, RecipeBase)]
    passed through recursive calls so that the *same* RecipeBase object is reused
    whenever the same package appears at multiple levels of the dep tree.  This is required
    for get_transitive_requires() (used by CMakeDeps) to correctly resolve header-transitive
    deps: it compares RecipeBase objects by identity, so the object for e.g. fast_float
    must be the same instance whether it appears in c4core's dep graph or in rapidyaml's.
    The platform and context are part of the key so a package built for the host and for
    the build machine stay distinct, including native builds where the same package is both
    a library dependency and a build tool.
    """
    deps_dict: OrderedDict[Requirement, RecipeBase] = OrderedDict()

    if _recipe_cache is None:
        _recipe_cache = {}

    def _add_dep(dep_name: str, is_build: bool, direct: bool = True) -> None:
        # Host deps inherit the parent's target; requires_tool (build context) reset to the
        # build machine.  Effective target fully determines the dep's settings + output folder.
        dep_os = None if is_build else target_os
        dep_arch = None if is_build else target_arch
        cache_key = (dep_name, dep_os, dep_arch, is_build)
        # If we already created a recipe for this dep+platform, reuse it.
        # This ensures object identity holds across all levels (needed by transitive_requires).
        if cache_key in _recipe_cache:
            cached_req, cached_recipe = _recipe_cache[cache_key]
            # Add to the current level's deps_dict with the appropriate directness flag.
            # Preserve run= so requires_tool keep run=True; VirtualBuildEnv only adds a
            # build dep's bindir to PATH when its requirement has run=True.
            existing = next((r for r in deps_dict if str(r.name) == dep_name and r.build == is_build), None)
            if existing is None:
                new_req = Requirement(
                    cached_req.ref, build=is_build, run=cached_req.run, direct=direct)
                deps_dict[new_req] = cached_recipe
            else:
                # A dep reached both transitively (direct=False) and as a direct require must
                # be marked direct so its buildenv propagates (e.g. pkgconf's PKG_CONFIG);
                # OR-in run so its bindir lands on PATH.
                if direct:
                    existing.direct = True
                if cached_req.run:
                    existing.run = True
            return

        recipe_path = recipes_root / dep_name / "recipe.py"
        if not recipe_path.exists():
            raise RecipeException(
                f"'{dep_name}' is required but has no recipe (recipes/{dep_name}/recipe.py). "
                f"Every dependency must be vendored: create that recipe, or remove the "
                f"requirement on '{dep_name}'.")

        dep_cls = _load_recipe_class(recipes_root, dep_name)
        dep_version = _resolve_version(dep_cls)

        dep = dep_cls()
        dep.version = dep_version
        dep.folders.set_recipe(recipes_root / dep_name)

        dep_settings = detect_settings(build_type, dep_os, dep_arch)
        if dep_os is None and dep_arch is None:
            dep_settings_build = dep_settings
        else:
            dep_settings_build = detect_settings(build_type)
        conf = Conf()
        conf.tools.build.jobs = jobs if jobs is not None else cpu_count()
        conf.tools.cmake.configure_args = []
        if not verbose:
            conf.tools.cmake.configure_args.append("-DCMAKE_POLICY_DEFAULT_CMP0092=NEW")
            # Silence CMake's "unused manually-specified variable CMAKE_POLICY_DEFAULT_CMP0092"
            # for projects whose cmake_minimum_required is already >= 3.15 (CMP0092 defaults NEW).
            conf.tools.cmake.configure_args.append("--no-warn-unused-cli")
        # Quiet by default (small CI logs); `build --verbose` restores full build-tool output
        # and compiler warnings. "-w" is safe on MSVC too: CMP0092=NEW drops the default /W3.
        conf.tools.build.verbose = verbose
        conf.tools.compilation.verbose = verbose
        if not verbose:
            conf.tools.build.cflags = [*conf.tools.build.cflags, "-w"]
            conf.tools.build.cxxflags = [*conf.tools.build.cxxflags, "-w"]
        _set_linux_compiler_executables(conf, dep_settings)
        _set_linux_build_compiler_executables(conf, dep_settings_build)
        dep._state = RecipeState(
            dependencies=RecipeDependencies(OrderedDict()),
            build_context=is_build,
            settings=dep_settings,
            settings_build=dep_settings_build,
            conf=conf,
            info=Info(set_defaults=True))

        # Package folder is keyed by the dep's own package_id (needs settings, set above).
        pkg_dir = str((_package_root(build_root, dep_name, _resolve_package_id(dep)) / "package").resolve())
        dep.folders.set_base_package(pkg_dir)

        # Full config phase (configure + auto-fPIC + package-type +
        # requirements); populates dep.requires for the sub-graph below.
        try:
            _run_configure_method(dep)
        except Exception:
            pass

        # Register in cache BEFORE recursing to handle diamond/cycle deps.
        ref = RecipeReference(dep_name)
        if is_build:
            req = Requirement(
                ref, headers=False, libs=False, build=True, run=True, direct=direct)
        else:
            # Set run=True if the package contains shared libraries so that
            # VirtualRunEnv adds its lib dir to DYLD_LIBRARY_PATH / LD_LIBRARY_PATH.
            # Pattern is keyed on the dep's TARGET os (not the build machine).
            from thirdparty._internal.util.detect import normalize_os, _machine_os
            _dep_os = normalize_os(dep_os) or _machine_os()
            _lib_path = Path(pkg_dir) / "lib"
            if _dep_os == "Mac":
                _pattern = "*.dylib"
            elif _dep_os in ("Windows", "WindowsStore"):
                _pattern = "*.dll"
            else:
                _pattern = "*.so*"
            _is_shared = _lib_path.is_dir() and any(_lib_path.glob(_pattern))
            req = Requirement(ref, build=False, run=_is_shared, direct=direct)
        _recipe_cache[cache_key] = (req, dep)
        deps_dict[req] = dep

        # Populate dep's own transitive dep graph so generators can resolve
        # component dependencies (e.g. spirv-tools-core → spirv-headers).
        # dep._requires was already populated by run_configure_method above.
        try:
            _sub_host = [str(r.name) for r in dep._requires if not r.build]
            _sub_tools = [str(r.name) for r in dep._requires if r.build]
            dep._state.dependencies = _build_dep_graph(
                recipes_root, build_root, _sub_host, build_type, dep_os, dep_arch, jobs=jobs, verbose=verbose, tool_names=_sub_tools, _recipe_cache=_recipe_cache, )
        except Exception:
            dep._state.dependencies = RecipeDependencies(OrderedDict())

        # Also propagate all transitive (non-direct) deps of this dep up to the current
        # deps_dict.  This ensures that when CMakeDeps calls get_transitive_requires() to
        # resolve header-transitive dependencies (transitive_headers=True), the transitive
        # packages are present in the consumer's dep graph with the same recipe objects.
        for trans_req, trans_recipe in dep.dependencies._data.items():
            trans_name = str(trans_req.name)
            if not any(str(r.name) == trans_name and r.build == trans_req.build for r in deps_dict.keys()):
                non_direct_req = Requirement(
                    trans_req.ref, build=trans_req.build, run=trans_req.run, direct=False)
                deps_dict[non_direct_req] = trans_recipe

        if hasattr(dep, "package_info"):
            try:
                dep.package_info()
            except Exception as exc:
                _out.warn(f"package_info() failed for {dep_name}: {exc}")

        # Make all relative info paths absolute so generators don't assert.
        dep.info.set_relative_base_folder(pkg_dir)

    for dep_name in dep_names:
        _add_dep(dep_name, is_build=False, direct=True)
    for dep_name in (tool_names or []):
        _add_dep(dep_name, is_build=True, direct=True)

    return RecipeDependencies(deps_dict)


def _is_sourced(
    build_root: Path,
    name: str,
    package_id: str) -> bool:
    return (_package_root(build_root, name, package_id) / "source" / _COMPLETE_MARKER).is_file()


def _build_only_tools(rgraph: _Graph) -> set[str]:
    """Recipes that are *only* ever a ``requires_tool`` (never a regular ``requires``).

    These are pure build tools (cmake, ninja, nasm, ...) and are built for the BUILD
    MACHINE.  A recipe used as a regular dependency anywhere is host-context (built for the
    target), even if it is also used as a tool somewhere.  When not cross-compiling the host
    and build platforms are identical, so this classification is a no-op.
    """
    host_required: set[str] = set()
    tool_required: set[str] = set()
    for node in rgraph.nodes.values():
        host_required.update(node.host_deps)
        tool_required.update(node.tool_deps)
    return {n for n in tool_required if n not in host_required}


def _build_ordered(
    recipes_root: Path,
    build_root: Path,
    names: list[str],
    build_type: str,
    jobs: int | None,
    resume: str | None,
    dry_run: bool,
    force: bool,
    generate_only: bool,
    target_os: str | None,
    target_arch: str | None,
    fail_fast: bool = False,
    exact_set: set[str] | None = None,
    verbose: bool = False, ) -> None:
    rgraph = _Graph.build(
        recipes_root, names, build_type, jobs=jobs, transitive=True, target_os=target_os, target_arch=target_arch)
    order = rgraph.topo_order()

    if resume:
        if resume not in order:
            _out.error(f"--resume '{resume}' not found in build order")
            sys.exit(1)
        order = order[order.index(resume):]

    # Classify each node: pure build tools build for the build machine; everything else
    # builds for the target.  (When not cross-compiling these are the same platform.)
    build_only = _build_only_tools(rgraph)

    def _node_target(name: str) -> tuple[str | None, str | None]:
        return (None, None) if name in build_only else (target_os, target_arch)

    cross = bool(target_os or target_arch)
    label = f"{build_type}"
    if cross:
        label += f" -> {detect_platform_tag(target_os, target_arch)}"
    if exact_set is not None:
        label += "  [exact]"
    _out.info(f"\n=== Build Plan: {len(order)} recipes ({label}) ===")
    for i, name in enumerate(order, 1):
        node = rgraph[name]
        version = node.version
        n_to, n_ta = _node_target(name)
        _cls = node.recipe_cls or _try_load_recipe_class(recipes_root, name)
        n_id = (_compute_package_id(_cls, recipes_root, name, version, build_type, n_to, n_ta)
                if _cls else detect_platform_tag(n_to, n_ta))
        built = _is_built(build_root, name, version, n_id)
        if exact_set is not None and name not in exact_set:
            status = "[ref-only]"
        else:
            status = "[force]" if force else ("[built]" if built else "[pending]")
        ctx = "" if not cross else f"  ({n_id})"
        _out.info(f"  {i:3d}. {name}/{version}  {status}{ctx}")

    if dry_run:
        return

    _out.info()

    visited: set[tuple[str, str]] = set()
    results: list[tuple[str, str, float, str | None]] = []
    skipped: list[tuple[str, str | None]] = []
    unavailable: dict[str, str] = {}

    def _skip(name: str, reason: str | None = None, *, blocks_dependants: bool = False) -> None:
        skipped.append((name, reason))
        if blocks_dependants:
            unavailable[name] = reason or "skipped"

    def _blocked_dependencies(name: str) -> list[str]:
        node = rgraph[name]
        return sorted(
            dep for dep in node.all_deps
            if dep in unavailable and not (dep == name and dep in node.tool_deps))

    for name in order:
        cls = _try_load_recipe_class(recipes_root, name)
        if cls is None:
            _out.info(f"[thirdparty] SKIP {name} - cannot load recipe")
            _skip(name, "cannot load recipe", blocks_dependants=True)
            continue
        version = _resolve_version(cls)
        n_to, n_ta = _node_target(name)
        n_id = _compute_package_id(cls, recipes_root, name, version, build_type, n_to, n_ta)
        # --exact: only build the explicitly named recipes; the rest are graph context only
        # and must never be built, wiped, or touched here.
        if exact_set is not None and name not in exact_set:
            _skip(name, "ref-only")
            continue
        if not force and _is_built(build_root, name, version, n_id):
            _skip(name, "already built")
            visited.add((name, n_id))
            continue
        blocked_deps = _blocked_dependencies(name)
        if blocked_deps:
            reason = f"dependency failed/skipped: {', '.join(blocked_deps)}"
            _out.info(f"[thirdparty] SKIP {name}/{version} - {reason}")
            _skip(name, reason, blocks_dependants=True)
            continue
        t0 = time.time()
        try:
            _build_recipe(
                recipes_root, build_root, name, build_type, visited, n_to, n_ta, jobs=jobs, generate_only=generate_only, force=force, exact_set=exact_set, verbose=verbose)
            elapsed = time.time() - t0
            results.append((name, version, elapsed, None))
        except Exception as exc:
            elapsed = time.time() - t0
            results.append((name, version, elapsed, str(exc)))
            unavailable[name] = "failed"
            # The recipe opened a build group in _build_recipe; close it so the failure
            # summary and the next recipe aren't swallowed into the failed recipe's group.
            _out.group_end()
            _out.info(f"[thirdparty] FAIL {name}/{version}: {exc}")
            if fail_fast:
                import traceback
                traceback.print_exc()
                sys.exit(1)

    ok = [(n, v, t) for n, v, t, e in results if e is None]
    fail = [(n, v, e) for n, v, _t, e in results if e is not None]

    _out.info(f"\n{"=" * 70}")
    _out.info(f"=== Summary: {len(ok)} built, {len(fail)} failed, {len(skipped)} skipped ===")
    _out.info(f"{"=" * 70}")
    if ok:
        _out.info(f"\nBuilt ({len(ok)}):")
        for n, v, t in ok:
            _out.info(f"  OK   {n}/{v}  ({t:.1f}s)")
    if skipped:
        _out.info(f"\nSkipped ({len(skipped)}):")
        for n, reason in skipped:
            suffix = f" ({reason})" if reason else ""
            _out.info(f"  SKIP {n}{suffix}")
    if fail:
        _out.info(f"\nFailed ({len(fail)}):")
        for n, v, e in fail:
            _out.info(f"  FAIL {n}/{v}: {e}")
        sys.exit(1)


def _build_recipe(
    recipes_root: Path,
    build_root: Path,
    name: str,
    build_type: str,
    visited: set[tuple[str, str]],
    target_os: str | None,
    target_arch: str | None,
    jobs: int | None = None,
    generate_only: bool = False,
    force: bool = False,
    exact_set: set[str] | None = None,
    verbose: bool = False, ) -> list[str]:
    """Build *name* and all its transitive dependencies.

    ``target_os``/``target_arch`` are this recipe's *effective* target platform (the host
    context).  Tool dependencies (build context) are built for the BUILD MACHINE by resetting
    the target to ``(None, None)``; regular host dependencies inherit this recipe's target.

    ``exact_set`` (``--exact``): when not ``None``, only recipes whose name is in this set are
    actually built.  Every other recipe is still walked to resolve the dependency graph (so
    generators can reference its package folder) but is never sourced, built, packaged, or
    wiped - its pre-existing package folder is used as-is.

    Returns the ordered list of all transitive dep names for *name* (deepest
    first) so that the caller can populate its own dep graph.
    """
    recipe_cls = _load_recipe_class(recipes_root, name)
    version = _resolve_version(recipe_cls)
    package_id = _compute_package_id(
        recipe_cls, recipes_root, name, version, build_type, target_os, target_arch)

    # visited is keyed by (name, package_id) so a recipe builds once per distinct output
    # identity (universal deps collapse across targets; self-tool cross-compile still twice).
    key = (name, package_id)
    if key in visited:
        return []
    visited.add(key)

    # Probe the recipe to discover its direct dependencies (even when pre-built,
    # so we can return the correct transitive dep list to our caller).
    probe = _instantiate(
        recipe_cls, recipes_root, build_root, name, version, build_type, target_os, target_arch, jobs=jobs, verbose=verbose)
    direct_deps, direct_tools = _get_requires(probe)

    # Recursively build tool dependencies that have local recipes - for the BUILD MACHINE.
    for tool_name in direct_tools:
        if (recipes_root / tool_name / "recipe.py").exists():
            _build_recipe(
                recipes_root, build_root, tool_name, build_type, visited, None, None, jobs=jobs, generate_only=generate_only, force=force, exact_set=exact_set, verbose=verbose)

    # Recursively build deps (inheriting this recipe's target) and collect their dep lists.
    transitive: list[str] = []
    for dep_name in direct_deps:
        if not (recipes_root / dep_name / "recipe.py").exists():
            _out.warn(f"dep recipe not found, skipping: {dep_name}")
            continue
        sub = _build_recipe(
            recipes_root, build_root, dep_name, build_type, visited, target_os, target_arch, jobs=jobs, generate_only=generate_only, force=force, exact_set=exact_set, verbose=verbose)
        for d in sub:
            if d not in transitive:
                transitive.append(d)
        # dep_name itself is in visited after the recursive call (either it was
        # already there or it was just built).  Add it to our list if not yet present.
        if dep_name not in transitive:
            transitive.append(dep_name)

    # --exact: dependencies (above) are resolved for reference only.  If this recipe was not
    # explicitly named, return its transitive dep list without sourcing/building/packaging or
    # wiping anything - the existing package folder (if any) is left untouched.
    if exact_set is not None and name not in exact_set:
        return transitive

    if not generate_only and not force and _is_built(build_root, name, version, package_id):
        _out.info(f"[thirdparty] {name}/{version} already built - skipping")
        return transitive

    # A different-version folder is stale: wipe it, then stamp the write-once manifest.
    _invalidate_stale(build_root, name, version, package_id)
    _write_manifest(build_root, name, version, package_id)

    # Build the dependency graph for this recipe from all transitive deps.
    dep_graph = _build_dep_graph(
        recipes_root, build_root, transitive, build_type, target_os, target_arch, jobs=jobs, verbose=verbose, tool_names=direct_tools)

    _out.group_start(f"Building {name}/{version} ({build_type})")

    recipe = _instantiate(
        recipe_cls, recipes_root, build_root, name, version, build_type, target_os, target_arch, jobs=jobs, verbose=verbose)
    recipe._state.dependencies = dep_graph

    # Propagate conf from tool dependency info into recipe.conf so that, e.g.,
    # msys2's exported bash:path is visible when generate()/build() run.
    for _req, _dep_iface in dep_graph._data.items():
        if _req.build:
            dep_conf = _dep_iface.info.conf
            if dep_conf:
                recipe.conf.compose_conf(dep_conf)

    pkg_dir = Path(recipe.folders.package)
    build_dir = Path(recipe.folders.build)
    src_dir = Path(recipe.folders.source)

    if force:
        # Wipe all build artifacts so source(), build(), and package() run fresh.
        for _dir in (src_dir, build_dir, pkg_dir):
            _wipe(_dir)
    elif not (build_dir / _COMPLETE_MARKER).is_file():
        # If the build marker is absent, the previous run was interrupted or failed.
        # Start the next attempt from a clean build/package tree while leaving the
        # failed tree in place until that next attempt so its logs can be inspected.
        _wipe(build_dir)
        _wipe(pkg_dir)

    # Drive the recipe's full config phase (configure + default auto-fPIC +
    # requirements) then validate(), before creating any directories so
    # that packages unsupported on this platform (RecipeInvalidConfiguration) don't leave
    # empty build trees behind.
    try:
        _run_configure_method(recipe)
        recipe.validate()
    except Exception as _cfg_exc:
        from thirdparty.errors import RecipeInvalidConfiguration
        if isinstance(_cfg_exc, RecipeInvalidConfiguration):
            _out.info(f"[thirdparty] {name}/{version} not supported on this platform: {_cfg_exc} - skipping")
            _out.group_end()
            return transitive
        raise

    if not generate_only and type(recipe).source is not RecipeBase.source:
        src_folder = Path(recipe.folders.source)
        src_folder.mkdir(parents=True, exist_ok=True)
        # Only run source() once per package; skip if already completed successfully.
        if not _is_sourced(build_root, name, package_id):
            # Wipe any partial state from a previous failed source() attempt
            _wipe(src_folder)
            src_folder.mkdir(parents=True, exist_ok=True)
            # Run source() with CWD = source_folder (as Conan does) so that downloads/extracts
            # (e.g. get()'s transient archive) land in the build tree, not the directory the
            # user invoked the build from.
            _orig_cwd_src = os.getcwd()
            try:
                os.chdir(src_folder)
                recipe.source()
            finally:
                os.chdir(_orig_cwd_src)
            (src_folder / _COMPLETE_MARKER).write_text("")
    gen_folder = recipe.folders.generators if type(recipe).generate is not RecipeBase.generate else None
    if type(recipe).generate is not RecipeBase.generate:
        # Recipe generators write files with bare filenames and expect CWD == generators_folder
        # (the comment in CMakeDeps says "# Current directory is the generators_folder").
        # We must chdir there before calling generate() so files land in the build tree, not here.
        gen_folder = recipe.folders.generators
        if gen_folder:
            Path(gen_folder).mkdir(parents=True, exist_ok=True)
        _orig_cwd = os.getcwd()
        try:
            if gen_folder:
                os.chdir(gen_folder)
            recipe.generate()
        finally:
            os.chdir(_orig_cwd)
    # system recipe 2.27.1 generates recipe_deps_legacy.cmake but recipes may expect recipe_deps.cmake
    if gen_folder:
        _legacy = Path(gen_folder) / "recipe_deps_legacy.cmake"
        _recipe_deps = Path(gen_folder) / "recipe_deps.cmake"
        if _legacy.is_file() and not _recipe_deps.is_file():
            _recipe_deps.write_text(_legacy.read_text(encoding="utf-8"), encoding="utf-8")
    generate_aggregated_env(recipe)
    if not generate_only:
        if type(recipe).build is not RecipeBase.build:
            Path(recipe.folders.build).mkdir(parents=True, exist_ok=True)
            _orig_cwd_build = os.getcwd()
            try:
                os.chdir(recipe.folders.build)
                recipe.build()
            finally:
                os.chdir(_orig_cwd_build)
        if type(recipe).package is not RecipeBase.package:
            Path(recipe.folders.build).mkdir(parents=True, exist_ok=True)
            _wipe(recipe.folders.package)
            Path(recipe.folders.package).mkdir(parents=True, exist_ok=True)
            _orig_cwd_pkg = os.getcwd()
            try:
                os.chdir(recipe.folders.build)
                recipe.package()
            except Exception:
                _wipe(recipe.folders.package)
                raise
            finally:
                os.chdir(_orig_cwd_pkg)
        # Write the completion marker only after both build() and package() succeed.
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / _COMPLETE_MARKER).write_text("")

    _out.info(f"[thirdparty] {name}/{version} done -> {recipe.folders.package}")
    _out.group_end()
    return transitive
