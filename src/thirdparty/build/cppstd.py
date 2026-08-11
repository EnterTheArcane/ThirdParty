import operator

from thirdparty.errors import RecipeInvalidConfiguration, RecipeException

from typing import Any
from thirdparty.recipe import RecipeBase


# The toolchains are pinned (the packaged MSVC toolset, the packaged LLVM, Xcode's clang,
# the system gcc), so what each compiler defaults to and accepts is a fixed fact rather
# than the per-version ladders these used to be.
_GNU_CPPSTD = [
    "98", "gnu98", "11", "gnu11", "14", "gnu14", "17", "gnu17", "20", "gnu20", "23", "gnu23", "26", "gnu26",
]

_DEFAULT_CPPSTD = {
    "gcc": "gnu17",
    "clang": "gnu17",
    "apple-clang": "gnu17",
    # /std:c++14 is the MSVC front's default and there is no "gnu" notion for it.
    "msvc": "14",
    "clang-cl": "14",
}

_SUPPORTED_CPPSTD = {
    "gcc": _GNU_CPPSTD,
    "clang": _GNU_CPPSTD,
    "apple-clang": _GNU_CPPSTD,
    # https://learn.microsoft.com/en-us/cpp/build/reference/std-specify-language-standard-version
    # c++23 is only reachable through /std:c++latest; there is no c++26 yet.
    "msvc": ["14", "17", "20", "23"],
    "clang-cl": ["14", "17", "20", "23"],
}


def check_min_cppstd(recipe: RecipeBase, cppstd: Any, gnu_extensions: bool = False):
    """ Check if current cppstd fits the minimal version required.

        In case the current cppstd doesn't fit the minimal version required
        by cppstd, a RecipeInvalidConfiguration exception will be raised.

        settings.compiler_cxx_standard must be defined, otherwise RecipeInvalidConfiguration is raised

    :param recipe: The current recipe object. Always use ``self``.
    :param cppstd: Minimal cppstd version required
    :param gnu_extensions: GNU extension is required (e.g gnu17)
    """
    _check_cppstd(recipe, cppstd, operator.lt, gnu_extensions)


def check_max_cppstd(recipe: RecipeBase, cppstd: Any, gnu_extensions: bool = False):
    """ Check if current cppstd fits the maximum version required.

        In case the current cppstd doesn't fit the maximum version required
        by cppstd, a RecipeInvalidConfiguration exception will be raised.

        settings.compiler_cxx_standard must be defined, otherwise RecipeInvalidConfiguration is raised

    :param recipe: The current recipe object. Always use ``self``.
    :param cppstd: Maximum cppstd version required
    :param gnu_extensions: GNU extension is required (e.g gnu17)
    """
    _check_cppstd(recipe, cppstd, operator.gt, gnu_extensions)


def valid_min_cppstd(recipe: RecipeBase, cppstd: Any, gnu_extensions: bool = False) -> bool:
    """ Validate if current cppstd fits the minimal version required.

    :param recipe: The current recipe object. Always use ``self``.
    :param cppstd: Minimal cppstd version required
    :param gnu_extensions: GNU extension is required (e.g gnu17). This option ONLY works on Linux.
    :return: True, if current cppstd matches the required cppstd version. Otherwise, False.
    """
    try:
        check_min_cppstd(recipe, cppstd, gnu_extensions)
    except RecipeInvalidConfiguration:
        return False
    return True


def valid_max_cppstd(recipe: RecipeBase, cppstd: Any, gnu_extensions: bool = False) -> bool:
    """ Validate if current cppstd fits the maximum version required.

    :param recipe: The current recipe object. Always use ``self``.
    :param cppstd: Maximum cppstd version required
    :param gnu_extensions: GNU extension is required (e.g gnu17). This option ONLY works on Linux.
    :return: True, if current cppstd matches the required cppstd version. Otherwise, False.
    """
    try:
        check_max_cppstd(recipe, cppstd, gnu_extensions)
    except RecipeInvalidConfiguration:
        return False
    return True


def default_cppstd(recipe: RecipeBase, compiler: str | None = None):
    """
    Get the default ``compiler.cppstd`` for the "recipe.settings.compiler", or for the
    parameter "compiler" if specified.

    :param recipe: The current recipe object. Always use ``self``.
    :param compiler: Name of the compiler e.g. gcc
    :return: The default ``compiler.cppstd`` for the specified compiler
    """
    compiler = compiler or recipe.settings.compiler
    if not compiler:
        raise RecipeException("Called default_cppstd with no compiler")
    return _DEFAULT_CPPSTD.get(compiler)


def supported_cppstd(recipe: RecipeBase, compiler: str | None = None):
    """
    Get a list of supported ``compiler.cppstd`` for the "recipe.settings.compiler", or for
    the parameter "compiler" if specified.

    :param recipe: The current recipe object. Always use ``self``.
    :param compiler: Name of the compiler e.g: gcc
    :return: a list of supported ``cppstd`` values.
    """
    compiler = compiler or recipe.settings.compiler
    if not compiler:
        raise RecipeException("Called supported_cppstd with no compiler")
    return _SUPPORTED_CPPSTD.get(compiler)


def _check_cppstd(
    recipe: RecipeBase,
    cppstd: Any,
    comparator: Any,
    gnu_extensions: bool):
    """ Check if current cppstd fits the version required according to a given comparator.

        In case the current cppstd doesn't fit the maximum version required
        by cppstd, a RecipeInvalidConfiguration exception will be raised.

        settings.compiler_cxx_standard must be defined, otherwise RecipeInvalidConfiguration is raised

    :param recipe: The current recipe object. Always use ``self``.
    :param cppstd: Required cppstd version.
    :param comparator: Operator to use to compare the detected and the required cppstd versions.
    :param gnu_extensions: GNU extension is required (e.g gnu17)
    """
    if not str(cppstd).isdigit():
        raise RecipeException("cppstd parameter must be a number")

    def compare(lhs: Any, rhs: Any, comp: Any) -> bool:
        def extract_cpp_version(_cppstd: Any) -> str:
            return str(_cppstd).replace("gnu", "")

        def add_millennium(_cppstd: Any) -> str:
            return "19%s" % _cppstd if _cppstd == "98" else "20%s" % _cppstd

        lhs = add_millennium(extract_cpp_version(lhs))
        rhs = add_millennium(extract_cpp_version(rhs))
        return not comp(lhs, rhs)

    current_cppstd = recipe.settings.compiler_cxx_standard
    if current_cppstd is None:
        raise RecipeInvalidConfiguration("The compiler.cppstd is not defined for this configuration")

    if gnu_extensions and "gnu" not in current_cppstd:
        raise RecipeInvalidConfiguration("The cppstd GNU extension is required")

    if not compare(current_cppstd, cppstd, comparator):
        raise RecipeInvalidConfiguration(
            f"Current cppstd ({current_cppstd}) is "
            f"{"higher" if comparator == operator.gt else "lower"} "
            f"than the required C++ standard ({cppstd}).")
