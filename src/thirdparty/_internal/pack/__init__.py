"""Pluggable package backends: turn a staged package folder into a distributable artifact.

Importing this package registers the built-in **archive** backends (``tar``, ``tar.gz``,
``tar.bz2``, ``tar.xz``, ``zip``) into :data:`BACKENDS`; select one with :func:`get_backend`.
The OCI image backend (:class:`~thirdparty._internal.pack.oci.OciBackend`) is used directly by
the ``oci`` command rather than through this registry."""

from thirdparty._internal.pack.backend import BACKENDS, PackageBackend, get_backend, register
from thirdparty._internal.pack.meta import PackageMeta, gather_meta, oci_arch, oci_os

# Import the archive backends so their register() side effects run on package import.
from thirdparty._internal.pack import archive as _archive  # noqa: F401  # pyright: ignore[reportUnusedImport]

ARCHIVE_DEFAULT_FORMAT = "tar.gz"

__all__ = [
    "BACKENDS",
    "PackageBackend",
    "get_backend",
    "register",
    "PackageMeta",
    "gather_meta",
    "oci_arch",
    "oci_os",
    "ARCHIVE_DEFAULT_FORMAT",
]
