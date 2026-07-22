import inspect
import os
import shutil
import sys
import traceback
import uuid
from collections import OrderedDict
from importlib import util as imp_util
from multiprocessing import cpu_count
from pathlib import Path
from threading import Lock
from typing import Any, cast

from thirdparty._internal.errors import NotFoundException
from thirdparty._internal.model.conf import Conf
from thirdparty._internal.model.dependencies import RecipeDependencies
from thirdparty._internal.model.info import Info
from thirdparty._internal.model.recipe import RecipeBase
from thirdparty._internal.model.settings import Settings
from thirdparty._internal.model.state import RecipeState
from thirdparty._internal.util.detect import detect_settings, platform_tag
from thirdparty._internal.util.files import chdir
from thirdparty.errors import RecipeException


class RecipeLoader:
    """Loads and caches recipe CLASSES from ``recipes/<name>/recipe.py``.

    The parsed recipe class is cached per path, so repeated lookups - version injection
    during ``requirements()``, the config-probe, graph resolution - don't re-parse the same
    file.  Instantiation is left to the caller (``make_probe_recipe`` / build.py), since each
    build/probe needs a fresh recipe object with its own folders + settings.
    """

    def __init__(self):
        self._cache: dict[str, type[RecipeBase] | None] = {}

    def load_class(self, recipes_root: Path, name: str) -> type[RecipeBase] | None:
        recipe_path = Path(recipes_root) / name / "recipe.py"
        key = str(recipe_path)
        if key not in self._cache:
            self._cache[key] = self._parse_class(recipe_path)
        return self._cache[key]

    @staticmethod
    def _parse_class(recipe_path: Path) -> type[RecipeBase] | None:
        if not recipe_path.exists():
            return None
        try:
            _module, cls = _parse_recipe(str(recipe_path))
            if not (isinstance(cls, type) and issubclass(cls, RecipeBase)):  # pyright: ignore[reportUnnecessaryIsInstance]  # defensive: _parse_recipe may return non-class objects
                return None
            return cls
        except Exception:
            return None


def _parse_module(recipe_module: Any, module_id: Any) -> type[RecipeBase]:
    """ Parses a python in-memory module, to extract the class defining the Recipe.
    @param recipe_module: the module to be processed
    @return: the main RecipeBase class from the module
    """
    result: type[RecipeBase] | None = None
    for name, attr in recipe_module.__dict__.items():
        if (name.startswith("_") or not inspect.isclass(attr) or attr.__dict__.get("__module__") != module_id):
            continue

        if issubclass(attr, RecipeBase) and attr != RecipeBase:
            if result is None:
                result = cast("type[RecipeBase]", attr)
            else:
                raise RecipeException("More than 1 recipe in the file")

    if result is None:
        raise RecipeException("No subclass of RecipeBase")

    return result


_load_python_lock = Lock()  # Loading our Python files is not thread-safe (modifies sys)


def _parse_recipe(recipe_path: Any):
    with _load_python_lock:
        module, module_id = _load_python_file(recipe_path)
    try:
        recipe = _parse_module(module, module_id)
        return module, recipe
    except Exception as e:  # re-raise with file name
        raise RecipeException("%s: %s" % (recipe_path, str(e)))


# Shared loader instance: caches parsed recipe classes so repeated lookups (version
# injection during requirements(), the config-probe, graph resolution) don't re-parse the
# same recipe.py file.
_RECIPE_LOADER = RecipeLoader()


def try_load_recipe_class(recipes_root: Path, name: str) -> type[RecipeBase] | None:
    """Load (and cache) the recipe class from ``recipes/<name>/recipe.py``.

    Delegates to the shared :class:`RecipeLoader`, which parses the file under a lock with a
    unique module id, inserts the recipe directory on ``sys.path`` so recipes can import
    sibling helpers, validates that exactly one RecipeBase subclass is defined, and caches
    the result.  Returns ``None`` if the recipe is missing or fails to load/validate.
    """
    return _RECIPE_LOADER.load_class(recipes_root, name)


def resolve_version(recipe_cls: type[RecipeBase]) -> str:
    v = getattr(recipe_cls, "version", None)
    return str(v) if v else "latest"


_LINUX_GCC_TRIPLETS = {"X64": "x86_64-linux-gnu", "ARM": "aarch64-linux-gnu"}


def _linux_gcc_compiler_executables(settings: Settings) -> dict[str, str] | None:
    """Return {"c": <cc>, "cpp": <cxx>} triplet-prefixed gcc executables for ``settings``, or None
    when the platform/compiler isn't Linux/gcc or the triplet compilers aren't installed."""
    if str(settings.os) != "Linux" or str(settings.compiler) != "gcc":
        return None
    triplet = _LINUX_GCC_TRIPLETS.get(str(settings.arch))
    if not triplet:
        return None
    cc = shutil.which(f"{triplet}-gcc") or shutil.which("gcc")
    cxx = shutil.which(f"{triplet}-g++") or shutil.which("g++")
    if cc and cxx:
        return {"c": cc, "cpp": cxx}
    return None


def set_linux_compiler_executables(conf: Conf, settings: Settings) -> None:
    """On Linux/gcc, point CMAKE_C/CXX_COMPILER (and autotools CC/CXX) at the target-triplet
    compiler. The minimal build container ships only triplet-prefixed compilers
    (x86_64-linux-gnu-gcc / aarch64-linux-gnu-gcc, no bare gcc/cc), and selecting by triplet
    also drives arm64 cross builds from an x64 host. No-op on other platforms/compilers.
    """
    execs = _linux_gcc_compiler_executables(settings)
    if execs:
        conf.tools.build.compiler_executables = cast("dict[Any, Any]", execs)


def set_linux_build_compiler_executables(conf: Conf, settings_build: Settings) -> None:
    """Populate the BUILD-machine compiler executables (used for CC_FOR_BUILD/CXX_FOR_BUILD when
    cross-compiling). Derived from ``settings_build`` so it tracks the build host's compiler rather
    than the (cross) target's. No-op on non-Linux/gcc build machines.
    """
    execs = _linux_gcc_compiler_executables(settings_build)
    if execs:
        conf.tools.build.compiler_executables_build = cast("dict[Any, Any]", execs)


def make_probe_recipe(
    recipe_cls: type[RecipeBase],
    recipes_root: Path,
    name: str,
    version: str,
    build_type: str,
    jobs: int | None = None,
    target_os: str | None = None,
    target_arch: str | None = None,
    verbose: bool = False) -> RecipeBase:
    """Instantiate a recipe with just enough state (settings, conf, requires shim) to
    drive ``configure()``/``requirements()``.

    ``target_os``/``target_arch`` select the HOST/target platform (default: build machine).
    ``settings`` is the target platform; ``settings_build`` is always the build machine.
    No build folders are created - this is for dependency discovery only.  ``build.py``
    layers folder setup on top of this for actual builds.
    """
    recipe = recipe_cls()
    recipe.version = version
    recipe.folders.set_recipe(recipes_root / name)

    settings = detect_settings(build_type, target_os, target_arch)
    if target_os is None and target_arch is None:
        settings_build = settings
    else:
        settings_build = detect_settings(build_type)
    conf = Conf()
    conf.tools.build.jobs = jobs if jobs is not None else cpu_count()
    conf.tools.cmake.configure_args = []
    if not verbose:
        # Drop CMake's default MSVC /W3 (kept for cmake_minimum_required < 3.15 via CMP0092=OLD)
        # so our injected /w is the only warning flag -> no "D9025: overriding '/w' with '/W3'".
        conf.tools.cmake.configure_args.append("-DCMAKE_POLICY_DEFAULT_CMP0092=NEW")
        # Projects whose cmake_minimum_required is already >= 3.15 default CMP0092 to NEW without
        # consulting the -D above, so CMake reports it as an unused manually-specified variable.
        # Suppress that (and any other unused framework-injected -D) cosmetic warning.
        conf.tools.cmake.configure_args.append("--no-warn-unused-cli")
    # Quiet by default so CI logs stay small (only the compiled file + errors); `build
    # --verbose` restores full build-tool output and compiler warnings.
    conf.tools.build.verbose = verbose
    conf.tools.compilation.verbose = verbose
    # Suppress compiler warnings when quiet. "-w" (== /w on cl) works for every compiler; on
    # MSVC the CMake toolchain also sets CMP0092=NEW so the default /W3 is gone and /w is the
    # only warning flag (no "D9025: overriding '/w' with '/W3'" spam).
    if not verbose:
        conf.tools.build.cflags = [*conf.tools.build.cflags, "-w"]
        conf.tools.build.cxxflags = [*conf.tools.build.cxxflags, "-w"]
    set_linux_compiler_executables(conf, settings)
    set_linux_build_compiler_executables(conf, settings_build)
    # Give the probe state so recipes can read settings/conf/context
    # during config/requirements (e.g. cross-build recipes doing requires_tool(self.name)).
    recipe._state = RecipeState(
        dependencies=RecipeDependencies(OrderedDict()),
        build_context=False,
        settings=settings,
        settings_build=settings_build,
        conf=conf,
        info=Info(set_defaults=True))
    return recipe


def resolve_package_id(recipe: RecipeBase) -> str:
    """Recipe's package_id, substituting the default ``<os>-<arch>`` when it returns None."""
    return recipe.package_id() or platform_tag(recipe.settings)


def compute_package_id(
    recipe_cls: type[RecipeBase], recipes_root: Path, name: str, version: str, build_type: str = "Release", target_os: str | None = None, target_arch: str | None = None) -> str:
    """Resolve a recipe's package_id for a target via a cheap settings-only probe."""
    probe = make_probe_recipe(recipe_cls, recipes_root, name, version, build_type, target_os=target_os, target_arch=target_arch)
    return resolve_package_id(probe)


def load_python_file(recipe_path: Any):
    """ From a given path, obtain the in memory python import module
    """
    with _load_python_lock:
        module, module_id = _load_python_file(recipe_path)
    return module, module_id


def _load_python_file(recipe_path: Any):
    """ From a given path, obtain the in memory python import module
    """

    if not os.path.exists(recipe_path):
        raise NotFoundException("%s not found!" % recipe_path)

    def new_print(*args: Any, **kwargs: Any):  # Make sure that all user python files print() goes to stderr
        kwargs.setdefault("file", sys.stderr)
        print(*args, **kwargs)

    module_id = str(uuid.uuid1())
    current_dir = os.path.dirname(recipe_path)
    sys.path.insert(0, current_dir)
    try:
        old_modules = list(sys.modules.keys())
        with chdir(current_dir):
            old_dont_write_bytecode = sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode = True
                spec = imp_util.spec_from_file_location(module_id, recipe_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Could not load spec for {recipe_path}")
                loaded = imp_util.module_from_spec(spec)
                spec.loader.exec_module(loaded)
                sys.dont_write_bytecode = old_dont_write_bytecode
            except ImportError:
                raise

        # These lines are necessary, otherwise local recipe imports with same name
        # collide, but no error, and overwrite other packages imports!!
        added_modules = set(sys.modules).difference(old_modules)
        for added in added_modules:
            module = sys.modules[added]
            if module:
                try:
                    try:
                        # Most modules will have __file__ != None
                        folder: str = os.path.dirname(cast("str", module.__file__))
                    except (AttributeError, TypeError):
                        # But __file__ might not exist or equal None
                        # Like some builtins and Namespace packages py3
                        folder = cast("Any", module.__path__)._path[0]
                except AttributeError:  # In case the module.__path__ doesn't exist
                    pass
                else:
                    if folder.startswith(current_dir):
                        module = sys.modules.pop(added)
                        cast("Any", module).print = new_print
                        sys.modules["%s.%s" % (module_id, added)] = module
    except RecipeException:
        raise
    except Exception:
        trace = traceback.format_exc().split("\n")
        raise RecipeException(
            "Unable to load recipe in %s\n%s" % (
                recipe_path, "\n".join(trace[3:]),
            ))
    finally:
        sys.path.pop(0)

    cast("Any", loaded).print = new_print
    return loaded, module_id
