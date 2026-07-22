import os
import subprocess
from typing import IO, Any, cast

from thirdparty._internal.output import Output, Color, LEVEL_QUIET
from thirdparty.errors import RecipeException
from thirdparty.recipe import RecipeBase


def run(
    recipe: RecipeBase,
    command: str,
    stdout: IO[Any] | int | None = None,
    cwd: str | None = None,
    ignore_errors: bool = False,
    env: str | list[str] | None = "",
    quiet: bool = False,
    shell: bool = True,
    scope: str = "build",
    stderr: IO[Any] | int | None = None) -> int:
    """ Run a command in the recipe's package context.

    :parameter recipe: the current recipe, always pass ``self``.
    :parameter command: The command to run.
    :parameter stdout: The output stream to write the command output. If ``None``, it defaults to
        the standard output stream.
    :parameter stderr: The error output stream to write the command error output. If ``None``,
        it defaults to the standard error stream.
    :parameter cwd: The current working directory to run the command in.
    :parameter ignore_errors: If ``True``, do not raise an error if the command returns a
        non-zero exit code.
    :parameter env: The environment file to use. If empty, it defaults to ``"env_build"`` for
        when ``scope`` is ``build`` or ``"env_run"`` for ``run`` (the aggregated environment
        files produced by ``generate_aggregated_env``, which include vcvars on Windows).
        If set to ``None`` explicitly, no environment file will be applied,
        which is useful for commands that do not require any environment.
    :parameter quiet: If ``True``, suppress the output of the command.
    :parameter shell: If ``True``, run the command in a shell. This is passed to the
        underlying ``Popen`` function.
    :parameter scope: The scope of the command, either ``"build"`` or ``"run"``.
    """
    # Import lazily to avoid any import-time cycle (mirrors how the old method imported
    # run_command lazily); command_env_wrapper pulls in thirdparty.build.
    from thirdparty._internal.subsystems import command_env_wrapper
    from thirdparty._internal.util.runners import run_command
    if env == "":  # This default allows not breaking for users with ``env=None`` indicating
        # they don't want any env-file applied
        env = "env_build" if scope == "build" else "env_run"

    env = [env] if env and isinstance(env, str) else (env or [])
    assert isinstance(env, list), "env argument to run() should be a list"
    envfiles_folder = os.fspath(recipe.folders.generators or os.getcwd())
    wrapped_cmd = command_env_wrapper(recipe, command, env, envfiles_folder=envfiles_folder, scope=scope)
    if not quiet:
        recipe.output.info(f"RUN: {command}", fg=Color.BRIGHT_BLUE)
    recipe.output.debug(f"Full command: {wrapped_cmd}")
    if quiet or Output.get_output_level() == LEVEL_QUIET:
        stdout = subprocess.DEVNULL if stdout is None else stdout
        stderr = subprocess.DEVNULL if stderr is None else stderr
    retcode = run_command(wrapped_cmd, cwd=cwd, stdout=cast("IO[Any] | None", stdout), stderr=cast("IO[Any] | None", stderr), shell=shell)
    if not quiet:
        recipe.output.writeln("")

    if not ignore_errors and retcode != 0:
        raise RecipeException(f"Error {retcode} while executing")

    return retcode
