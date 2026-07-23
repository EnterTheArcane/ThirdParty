import io
import json
import os
import tarfile
from pathlib import Path
from typing import Any

from thirdparty._internal.pack.digest import oci_digest, sha256_bytes


# OCI media types (image-spec v1.1).
OCI_LAYOUT_VERSION = "1.0.0"
MT_INDEX = "application/vnd.oci.image.index.v1+json"
MT_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
MT_CONFIG = "application/vnd.oci.image.config.v1+json"
MT_LAYER = "application/vnd.oci.image.layer.v1.tar+gzip"


def canonical_json(obj: Any) -> bytes:
    """Serialize *obj* to the byte form used for every digested OCI document.

    Keys sorted, tight separators, no trailing newline - so the same logical document
    always hashes to the same digest across runs and machines (reproducibility)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def descriptor(
    media_type: str,
    data: bytes,
    *,
    platform: "dict[str, Any] | None" = None,
    annotations: "dict[str, str] | None" = None) -> "dict[str, Any]":
    """Build an OCI descriptor (``mediaType``/``digest``/``size`` + optional extras) for *data*."""
    desc: dict[str, Any] = {
        "mediaType": media_type,
        "digest": oci_digest(data),
        "size": len(data),
    }
    if platform is not None:
        desc["platform"] = platform
    if annotations:
        desc["annotations"] = annotations
    return desc


def write_blob(blobs_dir: Path, data: bytes) -> str:
    """Write *data* into ``blobs/sha256/<hex>`` (the filename IS the digest) and return
    the ``sha256:<hex>`` reference.  Content-addressed, so re-writing an identical blob
    is idempotent."""
    hexd = sha256_bytes(data)
    blobs_dir.mkdir(parents=True, exist_ok=True)
    (blobs_dir / hexd).write_bytes(data)
    return "sha256:" + hexd


def _tarinfo(name: str) -> tarfile.TarInfo:
    """A TarInfo with all host-identifying metadata zeroed for reproducible archives."""
    ti = tarfile.TarInfo(name)
    ti.mtime = 0
    ti.uid = 0
    ti.gid = 0
    ti.uname = ""
    ti.gname = ""
    return ti


def build_deterministic_tar(
    root: Path,
    extra: "dict[str, bytes] | None" = None) -> bytes:
    """Return the bytes of a reproducible uncompressed tar of *root*.

    Entries are emitted in sorted order with fixed mtime/uid/gid and normalized modes, and
    every member name uses forward slashes (so archives built on Windows extract correctly
    everywhere).  Symlinks are stored as links, never dereferenced.  ``extra`` injects
    additional top-level members (e.g. a ``metadata.json`` sidecar) by name.

    Callers that want a gzip layer/archive gzip these bytes separately with ``mtime=0`` so
    the compression stays reproducible too."""
    buf = io.BytesIO()
    extra_map: "dict[str, bytes]" = extra or {}
    # PAX so long names / arbitrary metadata round-trip losslessly and deterministically.
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        _add_tree(tar, root)
        for name in sorted(extra_map):
            data = extra_map[name]
            ti = _tarinfo(name)
            ti.type = tarfile.REGTYPE
            ti.mode = 0o644
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def _add_tree(tar: tarfile.TarFile, root: Path) -> None:
    """Recursively add *root*'s contents to *tar* in sorted, symlink-preserving order."""

    def recurse(directory: str, rel: str) -> None:
        for name in sorted(os.listdir(directory)):
            full = os.path.join(directory, name)
            arcname = f"{rel}/{name}" if rel else name
            if os.path.islink(full):
                ti = _tarinfo(arcname)
                ti.type = tarfile.SYMTYPE
                ti.mode = 0o777
                ti.linkname = os.readlink(full).replace(os.sep, "/")
                tar.addfile(ti)
            elif os.path.isdir(full):
                ti = _tarinfo(arcname)
                ti.type = tarfile.DIRTYPE
                ti.mode = 0o755
                tar.addfile(ti)
                recurse(full, arcname)
            else:
                ti = _tarinfo(arcname)
                ti.type = tarfile.REGTYPE
                # Preserve the executable bit (matters for Linux binaries); otherwise 0644.
                executable = bool(os.stat(full).st_mode & 0o111)
                ti.mode = 0o755 if executable else 0o644
                ti.size = os.path.getsize(full)
                with open(full, "rb") as fh:
                    tar.addfile(ti, fh)

    recurse(str(root), "")
