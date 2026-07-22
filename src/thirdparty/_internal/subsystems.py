"""
Potential scenarios:

- Running from a Windows native "cmd"
  - Targeting Windows native (os.subsystem = None)
    - No need of bash (no conf at all)
    - Need to build in bash (tools.microsoft.bash:path=<path>, recipe.win_bash)
  - Targeting Subsystem (os.subsystem = msys2)
    - Always builds and runs in bash (tools.microsoft.bash:path)

- Running from a subsytem terminal (tools.microsoft.bash:active=True,
                                    tools.microsoft.bash:path=None)
  - Targeting Windows native (os.subsystem = None)
  - Targeting Subsystem (os.subsystem = msys2)

"""
import os
from pathlib import Path
import platform
import re

from thirdparty.build import cmd_args_to_string
from thirdparty.errors import RecipeException
from thirdparty.recipe import RecipeBase

WINDOWS = "windows"
MSYS2 = "msys2"


def command_env_wrapper(
    recipe: RecipeBase, command: str, envfiles: list[str], envfiles_folder: str, scope: str = "build") -> str:
    from thirdparty.env.environment import environment_wrap_command
    if getattr(recipe, "conf", None) is None:
        # TODO: No conf, no profile defined!! This happens at ``export()`` time
        #  Is it possible to run a run(self, ...) in export() in bash?
        #  Is it necessary? Shouldn't be
        return command

    active = recipe.conf.tools.microsoft.bash.active
    if platform.system() == "Windows" and ((recipe.win_bash and scope == "build")):
        if active:
            wrapped_cmd = environment_wrap_command(recipe, envfiles, envfiles_folder, command)
        else:
            wrapped_cmd = _windows_bash_wrapper(recipe, command, envfiles, envfiles_folder)
    else:
        wrapped_cmd = environment_wrap_command(recipe, envfiles, envfiles_folder, command)
    return wrapped_cmd


def _windows_bash_wrapper(
    recipe: RecipeBase, command: str, env: list[str], envfiles_folder: str) -> str:
    from thirdparty.env import Environment
    from thirdparty.env.environment import environment_wrap_command
    """Will wrap a unix command inside an MSYS2 bash terminal."""

    subsystem = MSYS2
    if not platform.system() == "Windows":
        raise RecipeException("Command only for Windows operating system")

    shell_path = recipe.conf.tools.microsoft.bash.path
    if not shell_path:
        raise RecipeException(
            "The config 'conf.tools.microsoft.bash.path' is "
            "needed to run commands in a Windows subsystem")
    shell_path = Path(shell_path).as_posix()  # Should work in all terminals
    env = env or []
    if subsystem == MSYS2:
        # Configure MSYS2 to inherith the PATH
        msys2_mode_env = Environment()
        _msystem = {"x86": "MINGW32"}.get(recipe.settings.arch, "MINGW64")
        # https://www.msys2.org/wiki/Launchers/ dictates that the shell should be launched with
        # - MSYSTEM defined
        # - CHERE_INVOKING is necessary to keep the CWD and not change automatically to the user home
        msys2_mode_env.define("MSYSTEM", _msystem)
        msys2_mode_env.define("MSYS2_PATH_TYPE", "inherit")
        msys2_mode_env.unset("ORIGINAL_PATH")
        # So --login do not change automatically to the user home
        msys2_mode_env.define("CHERE_INVOKING", "1")
        path = os.path.join(recipe.folders.generators, "msys2_mode.bat")
        # Make sure we save pure .bat files, without sh stuff
        wb, recipe.win_bash = recipe.win_bash, None
        msys2_mode_env.vars(recipe, "build").save_bat(path)
        recipe.win_bash = wb
        env.append(path)

    wrapped_shell = '"%s"' % shell_path if " " in shell_path else shell_path
    wrapped_shell = environment_wrap_command(
        recipe, env, envfiles_folder, wrapped_shell, accepted_extensions=("bat", "ps1"))

    # Wrapping the inside_command enable to prioritize our environment, otherwise /usr/bin go
    # first and there could be commands that we want to skip
    wrapped_user_cmd = environment_wrap_command(
        recipe, env, envfiles_folder, command, accepted_extensions=("sh",))
    wrapped_user_cmd = _escape_windows_cmd(wrapped_user_cmd)
    # according to https://www.msys2.org/wiki/Launchers/, it is necessary to use --login shell
    # running without it is discouraged
    final_command = f"{wrapped_shell} --login -c {wrapped_user_cmd}"
    return final_command


def _escape_windows_cmd(command: str) -> str:
    """ To use in a regular windows cmd.exe
        1. Adds escapes so the argument can be unpacked by CommandLineToArgvW()
        2. Adds escapes for cmd.exe so the argument survives cmd.exe's substitutions.

        Useful to escape commands to be executed in a windows bash (msys2)
    """
    quoted_arg = cmd_args_to_string([command])
    return "".join(["^%s" % arg if arg in r'()%!^"<>&|' else arg for arg in quoted_arg])


def deduce_subsystem(recipe: RecipeBase, scope: str | None) -> str | None:
    """ used by:
    - EnvVars: to decide if using :  ; as path separator, translate paths to subsystem
               and decide to generate a .bat or .sh
    - Autotools: to define the full abs path to the "configure" script
    - GnuDeps: to map all the paths from dependencies
    - Aggregation of envfiles: to map each aggregated path to the subsystem
    - unix_path: util for recipes
    """
    scope = "build" if scope is None else scope  # let's assume build context if scope=None
    if scope.startswith("build"):
        the_os = recipe.settings_build.os
        if the_os is None:  # pyright: ignore[reportUnnecessaryComparison]  # os typed str but may be None at runtime
            raise RecipeException("The 'build' profile must have a 'os' declared")
    else:
        the_os = recipe.settings.os

    if not str(the_os).startswith("Windows"):
        return None

    active = recipe.conf.tools.microsoft.bash.active
    if active:
        return MSYS2

    if scope.startswith("build") or scope.startswith("run"):
        if recipe.win_bash:
            return MSYS2

    return WINDOWS


def subsystem_path(subsystem: str | None, path: str | os.PathLike[str]) -> str:
    """"Used to translate windows paths to MSYS2 unix paths like
    /c/users/path/to/file. Not working in a regular console or MinGW!
    """
    path = os.fspath(path)
    if subsystem is None or subsystem == WINDOWS:
        return path

    if os.path.exists(path):
        # if the path doesn't exist (and abs) we cannot guess the casing
        path = get_cased_path(path)

    if path.startswith("\\\\?\\"):
        path = path[4:]
    path = path.replace(":/", ":\\")
    pattern = re.compile(r"([a-z]):\\", re.IGNORECASE)
    path = pattern.sub("/\\1/", path).replace("\\", "/")

    return path.lower()


def get_cased_path(name: str) -> str:
    if platform.system() != "Windows":
        return name
    if not os.path.isabs(name):
        name = os.path.abspath(name)

    result: list[str] = []
    current = name
    while True:
        parent, child = os.path.split(current)
        if parent == current:
            break

        child_cased = child
        if os.path.exists(parent):
            children = os.listdir(parent)
            for c in children:
                if c.upper() == child.upper():
                    child_cased = c
                    break
        result.append(child_cased)
        current = parent
    drive, _ = os.path.splitdrive(current)
    result.append(drive)
    return os.sep.join(reversed(result))
