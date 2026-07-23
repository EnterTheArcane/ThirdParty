"""Pluggable package backends: turn a staged package folder into a distributable artifact.

Importing this package registers the built-in backends (``oci`` default, ``tar.gz``,
``zip``) into :data:`BACKENDS`; select one with :func:`get_backend`."""

from thirdparty._internal.pack.backend import BACKENDS, PackageBackend, get_backend, register
from thirdparty._internal.pack.meta import PackageMeta, gather_meta, oci_arch, oci_os

# Import the concrete backends so their register() side effects run on package import.
from thirdparty._internal.pack import oci as _oci  # noqa: F401  # pyright: ignore[reportUnusedImport]
from thirdparty._internal.pack import archive as _archive  # noqa: F401  # pyright: ignore[reportUnusedImport]

DEFAULT_FORMAT = "oci"

__all__ = [
    "BACKENDS",
    "PackageBackend",
    "get_backend",
    "register",
    "PackageMeta",
    "gather_meta",
    "oci_arch",
    "oci_os",
    "DEFAULT_FORMAT",
]
