import operator

from thirdparty._internal.model.version import Version
from thirdparty._internal.util.detect_api import default_cstd as default_cstd_
from thirdparty.errors import RecipeInvalidConfiguration, RecipeException

from typing import Any
from thirdparty.recipe import RecipeBase


def check_min_cstd(recipe: RecipeBase, cstd: Any, gnu_extensions: bool = False):
    """ Check if current cstd fits the minimal version required.

        In case the current cstd doesn't fit the minimal version required
        by cstd, a RecipeInvalidConfiguration exception will be raised.

        1. If settings.compiler_c_standard, the tool will use settings.compiler_c_standard to compare
        2. It not settings.compiler_c_standard, the tool will use compiler to compare (reading the
           default from cstd_default)
        3. If not settings.compiler is present (not declared in settings) will raise because it
           cannot compare.
        4. If can not detect the default cstd for settings.compiler, a exception will be raised.

    :param recipe: The current recipe object. Always use ``self``.
    :param cstd: Minimal cstd version required
    :param gnu_extensions: GNU extension is required (e.g gnu17)
    """
    _check_cstd(recipe, cstd, operator.lt, gnu_extensions)


def check_max_cstd(recipe: RecipeBase, cstd: Any, gnu_extensions: bool = False):
    """ Check if current cstd fits the maximum version required.

        In case the current cstd doesn't fit the maximum version required
        by cstd, a RecipeInvalidConfiguration exception will be raised.

        1. If settings.compiler_c_standard, the tool will use settings.compiler_c_standard to compare
        2. It not settings.compiler_c_standard, the tool will use compiler to compare (reading the
           default from cstd_default)
        3. If not settings.compiler is present (not declared in settings) will raise because it
           cannot compare.
        4. If can not detect the default cstd for settings.compiler, a exception will be raised.

    :param recipe: The current recipe object. Always use ``self``.
    :param cstd: Maximum cstd version required
    :param gnu_extensions: GNU extension is required (e.g gnu17)
    """
    _check_cstd(recipe, cstd, operator.gt, gnu_extensions)


def valid_min_cstd(recipe: RecipeBase, cstd: Any, gnu_extensions: bool = False) -> bool:
    """ Validate if current cstd fits the minimal version required.

    :param recipe: The current recipe object. Always use ``self``.
    :param cstd: Minimal cstd version required
    :param gnu_extensions: GNU extension is required (e.g gnu17). This option ONLY works on Linux.
    :return: True, if current cstd matches the required cstd version. Otherwise, False.
    """
    try:
        check_min_cstd(recipe, cstd, gnu_extensions)
    except RecipeInvalidConfiguration:
        return False
    return True


def valid_max_cstd(recipe: RecipeBase, cstd: Any, gnu_extensions: bool = False) -> bool:
    """ Validate if current cstd fits the maximum version required.

    :param recipe: The current recipe object. Always use ``self``.
    :param cstd: Maximum cstd version required
    :param gnu_extensions: GNU extension is required (e.g gnu17). This option ONLY works on Linux.
    :return: True, if current cstd matches the required cstd version. Otherwise, False.
    """
    try:
        check_max_cstd(recipe, cstd, gnu_extensions)
    except RecipeInvalidConfiguration:
        return False
    return True


def default_cstd(recipe: RecipeBase, compiler: str | None = None, compiler_version: Any = None):
    """
    Get the default ``compiler.cstd`` for the "recipe.settings.compiler" and "recipe
    settings.compiler_version" or for the parameters "compiler" and "compiler_version" if specified.

    :param recipe: The current recipe object. Always use ``self``.
    :param compiler: Name of the compiler e.g. gcc
    :param compiler_version: Version of the compiler e.g. 12
    :return: The default ``compiler.cstd`` for the specified compiler
    """
    compiler = compiler or recipe.settings.compiler
    compiler_version = compiler_version or recipe.settings.compiler_version
    if not compiler or not compiler_version:
        raise RecipeException("Called default_cppstd with no compiler or no compiler_version")
    return default_cstd_(compiler, Version(compiler_version))


def supported_cstd(recipe: RecipeBase, compiler: str | None = None, compiler_version: Any = None):
    """
    Get a list of supported ``compiler.cstd`` for the "recipe.settings.compiler" and
    "recipe.settings.compiler_version" or for the parameters "compiler" and "compiler_version"
    if specified.

    :param recipe: The current recipe object. Always use ``self``.
    :param compiler: Name of the compiler e.g: gcc
    :param compiler_version: Version of the compiler e.g: 12
    :return: a list of supported ``cstd`` values.
    """
    compiler = compiler or recipe.settings.compiler
    compiler_version = compiler_version or recipe.settings.compiler_version
    if not compiler or not compiler_version:
        raise RecipeException("Called supported_cstd with no compiler or no compiler_version")

    func = {
        "apple-clang": _apple_clang_supported_cstd, "gcc": _gcc_supported_cstd, "msvc": _msvc_supported_cstd, "clang": _clang_supported_cstd, "emcc": _emcc_supported_cstd,
    }.get(compiler)
    if func:
        return func(Version(compiler_version))
    return None


def _check_cstd(
    recipe: RecipeBase,
    cstd: Any,
    comparator: Any,
    gnu_extensions: bool):
    """ Check if current cstd fits the version required according to a given comparator.

        In case the current cstd doesn't fit the maximum version required
        by cstd, a RecipeInvalidConfiguration exception will be raised.

        1. If settings.compiler_c_standard, the tool will use settings.compiler_c_standard to compare
        2. It not settings.compiler_c_standard, the tool will use compiler to compare (reading the
           default from cstd_default)
        3. If not settings.compiler is present (not declared in settings) will raise because it
           cannot compare.
        4. If can not detect the default cstd for settings.compiler, a exception will be raised.

    :param recipe: The current recipe object. Always use ``self``.
    :param cstd: Required cstd version.
    :param comparator: Operator to use to compare the detected and the required cstd versions.
    :param gnu_extensions: GNU extension is required (e.g gnu17)
    """
    if not str(cstd).isdigit():
        raise RecipeException("cstd parameter must be a number")

    def compare(lhs: Any, rhs: Any, comp: Any) -> bool:
        def extract_cpp_version(_cstd: Any) -> str:
            return str(_cstd).replace("gnu", "")

        def add_millennium(_cstd: Any) -> str:
            return "19%s" % _cstd if _cstd == "99" else "20%s" % _cstd

        lhs = add_millennium(extract_cpp_version(lhs))
        rhs = add_millennium(extract_cpp_version(rhs))
        return not comp(lhs, rhs)

    current_cstd = recipe.settings.compiler_c_standard
    if current_cstd is None:
        raise RecipeInvalidConfiguration("The compiler.cstd is not defined for this configuration")

    if gnu_extensions and "gnu" not in current_cstd:
        raise RecipeInvalidConfiguration("The cstd GNU extension is required")

    if not compare(current_cstd, cstd, comparator):
        raise RecipeInvalidConfiguration(
            f"Current cstd ({current_cstd}) is "
            f"{"higher" if comparator == operator.gt else "lower"} "
            f"than the required C standard ({cstd}).")


def _apple_clang_supported_cstd(version: Any) -> list[str]:
    # TODO: Per-version support
    return ["99", "gnu99", "11", "gnu11", "17", "gnu17", "23", "gnu23"]


def _gcc_supported_cstd(version: Any) -> list[str]:
    if version < "4.7":
        return ["99", "gnu99"]
    if version < "8":
        return ["99", "gnu99", "11", "gnu11"]
    if version < "14":
        return ["99", "gnu99", "11", "gnu11", "17", "gnu17"]
    return ["99", "gnu99", "11", "gnu11", "17", "gnu17", "23", "gnu23"]


def _msvc_supported_cstd(version: Any) -> list[str]:
    if version < "192":
        return []
    return ["11", "17"]


def _clang_supported_cstd(version: Any) -> list[str]:
    if version < "3":
        return ["99", "gnu99"]
    if version < "6":
        return ["99", "gnu99", "11", "gnu11"]
    if version < "18":
        return ["99", "gnu99", "11", "gnu11", "17", "gnu17"]
    return ["99", "gnu99", "11", "gnu11", "17", "gnu17", "23", "gnu23"]


def _emcc_supported_cstd(version: Any) -> list[str]:
    """
    emcc is based on clang but follow different versioning scheme.
    """
    if version <= "3.0.1":
        return _clang_supported_cstd(Version("14"))
    if version <= "3.1.50":
        return _clang_supported_cstd(Version("18"))
    if version <= "4.0.1":
        return _clang_supported_cstd(Version("20"))
    # Since emcc 4.0.2 clang version is 21
    return _clang_supported_cstd(Version("21"))
