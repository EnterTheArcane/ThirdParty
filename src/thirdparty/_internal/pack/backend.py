from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from thirdparty._internal.pack.meta import PackageMeta
from thirdparty.errors import RecipeException


@runtime_checkable
class PackageBackend(Protocol):
    """A strategy that turns a staged package folder into a distributable artifact.

    Implementations register themselves via :func:`register`; ``package``/``publish`` pick
    one by ``--format`` through :func:`get_backend`."""

    name: str

    def pack(self, staged_dir: Path, out_dir: Path, meta: PackageMeta) -> Path:
        """Write the artifact for *meta* under *out_dir* and return the produced path.

        Archive backends return the archive file; the OCI backend returns the layout
        directory."""
        ...


BACKENDS: "dict[str, PackageBackend]" = {}


def register(backend: PackageBackend) -> None:
    BACKENDS[backend.name] = backend


def get_backend(name: str) -> PackageBackend:
    try:
        return BACKENDS[name]
    except KeyError:
        raise RecipeException(
            f"unknown package format '{name}'; choices: {', '.join(sorted(BACKENDS))}")
