import configparser
import os
import sys
from collections.abc import Iterable
from shlex import quote
from typing import Any

from thirdparty.build.compiler import check_min_compiler_version
from thirdparty.build.cppstd import check_max_cppstd, check_min_cppstd, valid_max_cppstd, valid_min_cppstd, default_cppstd, supported_cppstd
from thirdparty.build.cpu import build_jobs
from thirdparty.build.cross_building import cross_building, can_run
from thirdparty.build.cstd import check_max_cstd, check_min_cstd, valid_max_cstd, valid_min_cstd, default_cstd, supported_cstd
from thirdparty.build.flags import cppstd_flag
from thirdparty.build.stdcpp_library import stdcpp_library
from thirdparty.errors import RecipeException
from thirdparty.recipe import RecipeBase

RECIPE_TOOLCHAIN_ARGS_FILE = "buildenv.conf"
RECIPE_TOOLCHAIN_ARGS_SECTION = "toolchain"

__all__ = [
    "check_min_compiler_version",
    "check_max_cppstd", "check_min_cppstd", "valid_max_cppstd", "valid_min_cppstd",
    "default_cppstd", "supported_cppstd",
    "build_jobs",
    "cross_building", "can_run",
    "check_max_cstd", "check_min_cstd", "valid_max_cstd", "valid_min_cstd",
    "default_cstd", "supported_cstd",
    "cppstd_flag",
    "stdcpp_library",
    "use_win_mingw", "cmd_args_to_string", "load_toolchain_args", "save_toolchain_args",
    "RECIPE_TOOLCHAIN_ARGS_FILE", "RECIPE_TOOLCHAIN_ARGS_SECTION",
]


def use_win_mingw(recipe: RecipeBase) -> bool:
    os_build = recipe.settings_build.os
    if os_build == "Windows":
        compiler_ = recipe.settings.compiler
        sub = recipe.settings.os_subsystem
        if sub == "msys2" or compiler_ == "qcc":
            return False
        else:
            return True
    return False


def cmd_args_to_string(args: Iterable[str] | None) -> str:
    if not args:
        return ""
    if sys.platform == "win32":
        return _windows_cmd_args_to_string(args)
    else:
        return _unix_cmd_args_to_string(args)


def _unix_cmd_args_to_string(args: Iterable[str]) -> str:
    """Return a shell-escaped string from *split_command*."""
    return " ".join(quote(arg) for arg in args)


def _windows_cmd_args_to_string(args: Iterable[str]) -> str:
    # FIXME: This is not managing all the parsing from list2cmdline, but covering simplified cases
    ret: list[str] = []
    for arg in args:
        # escaped quotes have to escape the \ and then the ". Replace with <QUOTE> so next
        # replace doesn't interfere
        arg = arg.replace(r'\"', r"\\\<QUOTE>")
        # quotes have to be escaped
        arg = arg.replace(r'"', r'\"')

        # restore the quotes
        arg = arg.replace("<QUOTE>", '"')
        # if argument have spaces, quote it
        if " " in arg or "\t" in arg:
            ret.append(f'"{arg}"')
        else:
            ret.append(arg)
    return " ".join(ret)


def load_toolchain_args(
    generators_folder: str | None = None, namespace: str | None = None) -> configparser.SectionProxy:
    """
    Helper function to load the content of any RECIPE_TOOLCHAIN_ARGS_FILE

    :param generators_folder: `str` folder where is located the RECIPE_TOOLCHAIN_ARGS_FILE.
    :param namespace: `str` namespace to be prepended to the filename.
    :return: <class 'configparser.SectionProxy'>
    """
    namespace_name = f"{namespace}_{RECIPE_TOOLCHAIN_ARGS_FILE}" if namespace else RECIPE_TOOLCHAIN_ARGS_FILE
    args_file = os.path.join(generators_folder, namespace_name) if generators_folder else namespace_name
    toolchain_config = configparser.ConfigParser()
    toolchain_file = toolchain_config.read(args_file)
    if not toolchain_file:
        raise RecipeException(
            "The file %s does not exist. Please, make sure that it was not"
            " generated in another folder." % args_file)
    try:
        return toolchain_config[RECIPE_TOOLCHAIN_ARGS_SECTION]
    except KeyError:
        raise RecipeException(
            "The primary section [%s] does not exist in the file %s. Please, add it"
            " as the default one of all your configuration variables." % (RECIPE_TOOLCHAIN_ARGS_SECTION, args_file))


def save_toolchain_args(
    content: dict[str, Any], generators_folder: str | None = None, namespace: str | None = None):
    """
    Helper function to save the content into the RECIPE_TOOLCHAIN_ARGS_FILE

    :param content: `dict` all the information to be saved into the toolchain file.
    :param namespace: `str` namespace to be prepended to the filename.
    :param generators_folder: `str` folder where is located the RECIPE_TOOLCHAIN_ARGS_FILE
    """
    # Let's prune None values
    content_ = {k: v for k, v in content.items() if v is not None}
    namespace_name = f"{namespace}_{RECIPE_TOOLCHAIN_ARGS_FILE}" if namespace else RECIPE_TOOLCHAIN_ARGS_FILE
    args_file = os.path.join(generators_folder, namespace_name) if generators_folder else namespace_name
    toolchain_config = configparser.ConfigParser()
    toolchain_config[RECIPE_TOOLCHAIN_ARGS_SECTION] = content_
    with open(args_file, "w") as f:
        toolchain_config.write(f)
