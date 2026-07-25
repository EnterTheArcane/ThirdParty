from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from thirdparty._internal.graph import discover_requires, package_root
from thirdparty._internal.loader import (
    compute_package_id,
    make_probe_recipe,
    resolve_version,
    try_load_recipe_class,
)
from thirdparty._internal.model.profile import BuildProfile
from thirdparty.errors import RecipeException
from thirdparty.recipe import RecipeBase


# Canonical settings value -> OCI platform value.  OCI/Go name amd64/arm64 and
# windows/linux/darwin; our settings use X64/ARM and Windows/Linux/Mac.
_OCI_ARCH = {"X64": "amd64", "ARM": "arm64"}
_OCI_OS = {"Windows": "windows", "Linux": "linux", "Mac": "darwin"}


def oci_arch(arch: str) -> str:
    return _OCI_ARCH.get(arch, arch.lower())


def oci_os(os_name: str) -> str:
    return _OCI_OS.get(os_name, os_name.lower())


def _empty_options() -> "list[tuple[str, str]]":
    return []


def _empty_deps() -> "list[str]":
    return []


def _empty_info() -> "dict[str, Any]":
    return {}


@dataclass(frozen=True)
class PackageMeta:
    """Everything identifying a built package, gathered from its recipe's settings/options.

    Carried into OCI annotations and the archive-backend ``metadata.json`` sidecar so a
    package system can query/filter by os/arch/build_type/options without unpacking."""

    name: str
    version: str
    package_id: str
    os: str
    arch: str
    build_type: str
    compiler: "str | None" = None
    compiler_version: "str | None" = None
    compiler_libcxx: "str | None" = None
    compiler_runtime: "str | None" = None
    options: "list[tuple[str, str]]" = field(default_factory=_empty_options)
    deps: "list[str]" = field(default_factory=_empty_deps)
    info: "dict[str, Any]" = field(default_factory=_empty_info)

    def oci_os(self) -> str:
        return oci_os(self.os)

    def oci_arch(self) -> str:
        return oci_arch(self.arch)

    def options_str(self) -> str:
        """``name=value`` pairs joined by ``;`` (sorted) - the annotation form."""
        return ";".join(f"{k}={v}" for k, v in self.options)

    def to_json(self) -> "dict[str, Any]":
        return {
            "name": self.name,
            "version": self.version,
            "package_id": self.package_id,
            "os": self.os,
            "arch": self.arch,
            "build_type": self.build_type,
            "compiler": self.compiler,
            "compiler_version": self.compiler_version,
            "compiler_libcxx": self.compiler_libcxx,
            "compiler_runtime": self.compiler_runtime,
            "options": {k: v for k, v in self.options},
            "deps": list(self.deps),
            "info": self.info,
        }


def gather_meta(
    recipes_root: Path,
    build_root: Path,
    name: str,
    build_type: str = "Release",
    target_os: "str | None" = None,
    target_arch: "str | None" = None) -> "tuple[PackageMeta, Path]":
    """Resolve *name*'s built package: return its :class:`PackageMeta` and staged dir.

    Raises :class:`RecipeException` if the recipe can't load or the package has not been
    built (no non-empty ``build/<name>/<package_id>/package/``)."""
    cls = try_load_recipe_class(recipes_root, name)
    if cls is None:
        raise RecipeException(f"recipe not found: {name}")

    if not probe_redistributable(recipes_root, name):
        raise RecipeException(f"'{name}' is not redistributable")

    profile = BuildProfile(build_type=build_type, target_os=target_os, target_arch=target_arch)
    version = resolve_version(cls)
    package_id = compute_package_id(cls, recipes_root, name, version, profile)
    staged = package_root(build_root, name, package_id) / "package"
    if not staged.is_dir() or not any(staged.iterdir()):
        raise RecipeException(
            f"package not built: {name}/{version} ({package_id}); run 'thirdparty build {name}' first")

    probe = make_probe_recipe(cls, recipes_root, name, version, profile)

    # discover_requires drives the config phase (populating options + requires) best-effort.
    host_deps, _tool_deps = discover_requires(probe)

    options: list[tuple[str, str]] = []
    try:
        options = [(str(k), str(v)) for k, v in probe.options.items()]
    except Exception:
        options = []

    info: dict[str, Any] = {}
    try:
        # Enrich info with the recipe's consumption contract when it defines one; skip
        # (leaving info at defaults) if package_info() relies on build outputs we don't have.
        if type(probe).package_info is not RecipeBase.package_info:
            probe.package_info()
    except Exception:
        pass
    try:
        info = probe.info.serialize()
    except Exception:
        info = {}

    settings = probe.settings
    meta = PackageMeta(
        name=name,
        version=version,
        package_id=package_id,
        os=str(settings.os),
        arch=str(settings.arch),
        build_type=str(settings.build_type),
        compiler=_opt_str(settings.compiler),
        compiler_version=_opt_str(settings.compiler_version),
        compiler_libcxx=_opt_str(settings.compiler_libcxx),
        compiler_runtime=_opt_str(settings.compiler_runtime),
        options=options,
        deps=host_deps,
        info=info)
    return meta, staged


def _opt_str(value: Any) -> "str | None":
    return None if value is None else str(value)


def probe_redistributable(recipes_root: Path, name: str) -> bool:
    """Whether *name* may be archived/published, from a lightweight package_info probe."""
    cls = try_load_recipe_class(recipes_root, name)
    if cls is None:
        return True
    try:
        probe = make_probe_recipe(cls, recipes_root, name, resolve_version(cls))
    except Exception:
        return True
    try:
        probe.package_info()
    except Exception:
        pass  # recipes set info.redistributable first, before touching folders/deps
    return probe.info.redistributable
