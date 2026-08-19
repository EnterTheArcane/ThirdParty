from __future__ import annotations

import bz2
import gzip
import lzma
import os
import zipfile
from pathlib import Path

from thirdparty._internal.pack.backend import register
from thirdparty._internal.pack.layout import build_deterministic_tar, canonical_json
from thirdparty._internal.pack.meta import PackageMeta


_METADATA_NAME = "metadata.json"


def _artifact_stem(meta: PackageMeta) -> str:
    return f"{meta.name}-{meta.version}-{meta.package_id}"


def _sidecar(meta: PackageMeta) -> bytes:
    """The full PackageMeta as JSON, so non-OCI artifacts still carry queryable metadata."""
    return canonical_json(meta.to_json())


def _compress(data: bytes, compression: str) -> bytes:
    """Deterministically compress the tar bytes for the given tar sub-format.

    gzip forces ``mtime=0`` (otherwise it stamps the current time); bz2/lzma embed no
    timestamp, so all variants are reproducible."""
    if compression == "":
        return data
    if compression == "gz":
        return gzip.compress(data, compresslevel=6, mtime=0)
    if compression == "bz2":
        return bz2.compress(data, compresslevel=9)
    if compression == "xz":
        return lzma.compress(data, preset=6)
    raise ValueError(f"unknown tar compression '{compression}'")


class TarBackend:
    """A ``<name>-<version>-<package_id>.tar[.<comp>]`` with a ``metadata.json`` sidecar.

    Reuses the deterministic tar builder (sorted entries, zeroed mtime/uid/gid, symlinks
    preserved), then compresses reproducibly.  ``compression`` is ``""`` (plain tar), ``"gz"``,
    ``"bz2"`` or ``"xz"``."""

    def __init__(self, compression: str):
        self.compression = compression
        self.name = "tar" if compression == "" else f"tar.{compression}"

    def pack(self, staged_dir: Path, out_dir: Path, meta: PackageMeta) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        tar_bytes = build_deterministic_tar(staged_dir, extra={_METADATA_NAME: _sidecar(meta)})
        target = out_dir / f"{_artifact_stem(meta)}.{self.name}"
        target.write_bytes(_compress(tar_bytes, self.compression))
        return target


class ZipBackend:
    """A ``<name>-<version>-<package_id>.zip`` with a ``metadata.json`` sidecar.

    Sorted forward-slash entries and a fixed timestamp for reproducibility.  ZIP cannot
    portably store POSIX symlinks, so symlinked entries are written as regular files."""

    name = "zip"

    def pack(self, staged_dir: Path, out_dir: Path, meta: PackageMeta) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{_artifact_stem(meta)}.zip"
        fixed_time = (1980, 1, 1, 0, 0, 0)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for arcname, full in _sorted_files(staged_dir):
                zi = zipfile.ZipInfo(arcname, date_time=fixed_time)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                with open(full, "rb") as fh:
                    zf.writestr(zi, fh.read())
            meta_zi = zipfile.ZipInfo(_METADATA_NAME, date_time=fixed_time)
            meta_zi.compress_type = zipfile.ZIP_DEFLATED
            meta_zi.external_attr = 0o644 << 16
            zf.writestr(meta_zi, _sidecar(meta))
        return target


def _sorted_files(root: Path) -> "list[tuple[str, str]]":
    """(forward-slash arcname, absolute path) for every file below *root*, sorted.

    Symlinks are followed to their target file contents (ZIP stores no link records)."""
    out: list[tuple[str, str]] = []

    def recurse(directory: str, rel: str):
        for name in sorted(os.listdir(directory)):
            full = os.path.join(directory, name)
            arcname = f"{rel}/{name}" if rel else name
            if os.path.isdir(full) and not os.path.islink(full):
                recurse(full, arcname)
            elif os.path.isfile(full):
                out.append((arcname, full))

    recurse(str(root), "")
    return out


register(TarBackend(""))
register(TarBackend("gz"))
register(TarBackend("bz2"))
register(TarBackend("xz"))
register(ZipBackend())
