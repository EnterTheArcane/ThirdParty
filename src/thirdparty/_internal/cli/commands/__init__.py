import argparse
from collections.abc import Callable
from typing import TypeGuard

_COMMAND_ATTR = "_is_thirdparty_command"

# All command functions receive the parsed argparse.Namespace as their sole argument.
CommandFn = Callable[[argparse.Namespace], None]


def command(fn: CommandFn) -> CommandFn:
    """Decorator that registers a function as a CLI subcommand.

    The function name becomes the command name.  The docstring, if present,
    becomes the help text shown in ``thirdparty --help``.

    Each command function must accept exactly one argument: the
    ``argparse.Namespace`` produced by parsing the command's sub-parser.
    """
    setattr(fn, _COMMAND_ATTR, True)
    return fn


def is_command(obj: object) -> TypeGuard[CommandFn]:
    return callable(obj) and bool(getattr(obj, _COMMAND_ATTR, False))
