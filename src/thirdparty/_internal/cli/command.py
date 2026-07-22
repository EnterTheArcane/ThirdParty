import argparse
from collections.abc import Callable
from typing import Any, TypeGuard, overload

_COMMAND_ATTR = "_is_thirdparty_command"
_COMMAND_NAME_ATTR = "_thirdparty_command_name"

# All command functions receive the parsed argparse.Namespace as their sole argument.
CommandFn = Callable[[argparse.Namespace], None]


@overload
def command(fn: CommandFn) -> CommandFn: ...


@overload
def command(*, name: str) -> Callable[[CommandFn], CommandFn]: ...


def command(fn: CommandFn | None = None, *, name: str | None = None) -> Callable[..., Any]:
    """Decorator that registers a function as a CLI subcommand.

    Used bare (``@command``) the function name becomes the command name.  Pass
    ``@command(name="list")`` to override it - useful when the function name would
    shadow a builtin (the ``list`` command).  The docstring, if present, becomes the
    help text shown in ``thirdparty --help``.

    Each command function must accept exactly one argument: the
    ``argparse.Namespace`` produced by parsing the command's sub-parser.
    """

    def deco(f: CommandFn) -> CommandFn:
        setattr(f, _COMMAND_ATTR, True)
        setattr(f, _COMMAND_NAME_ATTR, name or f.__name__)
        return f

    return deco(fn) if fn is not None else deco


def is_command(obj: object) -> TypeGuard[CommandFn]:
    return callable(obj) and bool(getattr(obj, _COMMAND_ATTR, False))


def command_name(obj: CommandFn) -> str:
    return getattr(obj, _COMMAND_NAME_ATTR, obj.__name__)
