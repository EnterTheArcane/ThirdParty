import os
import sys
from contextlib import contextmanager
from collections.abc import Generator

# GitHub Actions sets GITHUB_ACTIONS=true for every step; only then do we emit the
# ::group::/::endgroup:: workflow commands that make each recipe collapsible in the log.
_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


def in_github_actions() -> bool:
    return _GITHUB_ACTIONS


def _emit(line: str = "") -> None:
    # Everything goes to stderr with an explicit flush. Build-tool subprocesses inherit fd 2
    # and write to it directly (in real time), so routing our own status lines to the same
    # stream keeps them correctly interleaved. Plain print() to stdout is block-buffered when
    # stdout is a pipe (as in CI), which otherwise dumps every status line at the end of the log.
    print(line, file=sys.stderr, flush=True)


def info(msg: str = "") -> None:
    _emit(msg)


def warn(msg: str) -> None:
    _emit(f"[thirdparty] warn: {msg}")


def error(msg: str) -> None:
    _emit(f"[thirdparty] error: {msg}")


def group_start(title: str) -> None:
    _emit(f"::group::{title}" if _GITHUB_ACTIONS else f"\n[thirdparty] === {title} ===\n")


def group_end() -> None:
    if _GITHUB_ACTIONS:
        _emit("::endgroup::")


@contextmanager
def group(title: str) -> Generator[None]:
    group_start(title)
    try:
        yield
    finally:
        group_end()
