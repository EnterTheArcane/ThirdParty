from __future__ import annotations

import gzip
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from thirdparty._internal.pack.backend import register
from thirdparty._internal.pack.digest import oci_digest
from thirdparty._internal.pack.layout import (
    MT_CONFIG,
    MT_INDEX,
    MT_LAYER,
    MT_MANIFEST,
    OCI_LAYOUT_VERSION,
    build_deterministic_tar,
    canonical_json,
    descriptor,
    write_blob,
)
from thirdparty._internal.pack.meta import PackageMeta


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _annotations(meta: PackageMeta, created: str) -> "dict[str, str]":
    """Standard ``org.opencontainers.image.*`` plus queryable ``io.o3de.thirdparty.*``.

    The ``io.o3de.thirdparty.os``/``.arch`` carry the canonical settings values (``Windows``,
    ``X64``) - distinct from the OCI ``platform`` (``windows``, ``amd64``) - so the package
    system can filter on the exact toolchain identity.  ``None`` fields are omitted."""
    ann: dict[str, str] = {
        "org.opencontainers.image.title": meta.name,
        "org.opencontainers.image.version": meta.version,
        "org.opencontainers.image.created": created,
        "io.o3de.thirdparty.name": meta.name,
        "io.o3de.thirdparty.version": meta.version,
        "io.o3de.thirdparty.package_id": meta.package_id,
        "io.o3de.thirdparty.os": meta.os,
        "io.o3de.thirdparty.arch": meta.arch,
        "io.o3de.thirdparty.build_type": meta.build_type,
    }
    optional: dict[str, "str | None"] = {
        "io.o3de.thirdparty.compiler": meta.compiler,
        "io.o3de.thirdparty.compiler_version": meta.compiler_version,
        "io.o3de.thirdparty.compiler_libcxx": meta.compiler_libcxx,
        "io.o3de.thirdparty.compiler_runtime": meta.compiler_runtime,
    }
    for key, value in optional.items():
        if value is not None:
            ann[key] = value
    if meta.options:
        ann["io.o3de.thirdparty.options"] = meta.options_str()
    if meta.deps:
        ann["io.o3de.thirdparty.deps"] = ",".join(meta.deps)
    if meta.info:
        ann["io.o3de.thirdparty.info"] = canonical_json(meta.info).decode("utf-8")
    return ann


class OciBackend:
    """Build a single-layer OCI image as an on-disk image layout (no Docker/daemon).

    Layout produced under *out_dir*::

        oci-layout                     {"imageLayoutVersion": "1.0.0"}
        index.json                     one manifest descriptor + platform + annotations
        blobs/sha256/<hex>             layer (gzip tar), config JSON, manifest JSON
    """

    name = "oci"

    def pack(self, staged_dir: Path, out_dir: Path, meta: PackageMeta) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        blobs_dir = out_dir / "blobs" / "sha256"
        created = _now_iso()

        # 1. Layer: deterministic tar of the staged files, then reproducible gzip.
        uncompressed = build_deterministic_tar(staged_dir)
        diff_id = oci_digest(uncompressed)
        layer_blob = gzip.compress(uncompressed, compresslevel=6, mtime=0)
        write_blob(blobs_dir, layer_blob)
        layer_desc = descriptor(MT_LAYER, layer_blob)

        # 2. Image config: the uncompressed digest (diff_id) is what rootfs references,
        #    NOT the compressed layer digest.
        config: dict[str, Any] = {
            "created": created,
            "architecture": meta.oci_arch(),
            "os": meta.oci_os(),
            "config": {},
            "rootfs": {"type": "layers", "diff_ids": [diff_id]},
            "history": [{
                "created": created,
                "created_by": "thirdparty package",
                "comment": f"{meta.name}/{meta.version}",
            }],
        }
        config_bytes = canonical_json(config)
        write_blob(blobs_dir, config_bytes)
        config_desc = descriptor(MT_CONFIG, config_bytes)

        # 3. Image manifest.
        annotations = _annotations(meta, created)
        manifest: dict[str, Any] = {
            "schemaVersion": 2,
            "mediaType": MT_MANIFEST,
            "config": config_desc,
            "layers": [layer_desc],
            "annotations": annotations,
        }
        manifest_bytes = canonical_json(manifest)
        write_blob(blobs_dir, manifest_bytes)

        # 4. index.json referencing the manifest with its platform (the queryable handle).
        desc_annotations = dict(annotations)
        desc_annotations["org.opencontainers.image.ref.name"] = meta.version
        manifest_desc = descriptor(
            MT_MANIFEST,
            manifest_bytes,
            platform={"architecture": meta.oci_arch(), "os": meta.oci_os()},
            annotations=desc_annotations)
        index: dict[str, Any] = {
            "schemaVersion": 2,
            "mediaType": MT_INDEX,
            "manifests": [manifest_desc],
        }
        (out_dir / "index.json").write_bytes(canonical_json(index))
        (out_dir / "oci-layout").write_bytes(
            canonical_json({"imageLayoutVersion": OCI_LAYOUT_VERSION}))
        return out_dir


register(OciBackend())
