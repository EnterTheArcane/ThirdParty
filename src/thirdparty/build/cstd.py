import operator

from thirdparty.errors import RecipeInvalidConfiguration, RecipeException

from typing import Any
from thirdparty.recipe import RecipeBase


# The toolchains are pinned (the packaged MSVC toolset, the packaged LLVM, Xcode's clang,
# the system gcc), so what each compiler defaults to and accepts is a fixed fact rather
# than the per-version ladders these used to be.
_GNU_CSTD = ["99", "gnu99", "11", "gnu11", "17", "gnu17", "23", "gnu23"]

_DEFAULT_CSTD = {
    "gcc": "gnu17",
    "clang": "gnu17",
    "apple-clang": "gnu17",
    # The MSVC front has no documented default cstd; /std: is not passed unless asked for.
    "msvc": None,
    "clang-cl": None,
}

_SUPPORTED_CSTD = {
    "gcc": _GNU_CSTD,
    "clang": _GNU_CSTD,
    "apple-clang": _GNU_CSTD,
    "msvc": ["11", "17"],
    "clang-cl": ["11", "17"],
}


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


def default_cstd(recipe: RecipeBase, compiler: str | None = None):
    """
    Get the default ``compiler.cstd`` for the "recipe.settings.compiler", or for the
    parameter "compiler" if specified.

    :param recipe: The current recipe object. Always use ``self``.
    :param compiler: Name of the compiler e.g. gcc
    :return: The default ``compiler.cstd`` for the specified compiler
    """
    compiler = compiler or recipe.settings.compiler
    if not compiler:
        raise RecipeException("Called default_cstd with no compiler")
    return _DEFAULT_CSTD.get(compiler)


def supported_cstd(recipe: RecipeBase, compiler: str | None = None):
    """
    Get a list of supported ``compiler.cstd`` for the "recipe.settings.compiler", or for
    the parameter "compiler" if specified.

    :param recipe: The current recipe object. Always use ``self``.
    :param compiler: Name of the compiler e.g: gcc
    :return: a list of supported ``cstd`` values.
    """
    compiler = compiler or recipe.settings.compiler
    if not compiler:
        raise RecipeException("Called supported_cstd with no compiler")
    return _SUPPORTED_CSTD.get(compiler)


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
