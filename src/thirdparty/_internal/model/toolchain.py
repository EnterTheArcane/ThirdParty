from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields
from typing import Any


COMPILER_LANGUAGES = (
    "c", "cpp", "objc", "objcpp", "rc", "asm", "cuda", "fortran", "hip", "ispc")

_PATH_FIELDS = (
    "ar", "ranlib", "nm", "strip", "objcopy", "mt", "lib", "linker",
    "sysroot", "gcc_toolchain", "apple_sysroot", "cmake_toolchain_file")
_PATH_LIST_FIELDS = ("msvc_include_dirs", "msvc_lib_dirs")


@dataclass
class ToolchainInfo:
    """The toolchain contract a provider recipe publishes via ``self.info.toolchain``.

    Every Info carries an (empty) instance; a recipe that populates it in
    ``package_info()`` is a toolchain provider. Providers are host-context
    dependencies, so ``self.settings`` is the target platform and every per-target
    value here (triple, sysroot, SDK paths) is resolved for the exact target.
    """

    compilers: dict[str, str] = field(default_factory=dict)
    front_kind: str | None = None  # "gnu" | "clang" | "clang-cl" | "msvc"
    family: str | None = None
    version: str | None = None

    ar: str | None = None
    ranlib: str | None = None
    nm: str | None = None
    strip: str | None = None
    objcopy: str | None = None
    mt: str | None = None
    lib: str | None = None
    linker: str | None = None
    use_ld_flag: str | None = None

    target_triple: str | None = None
    system_processor: str | None = None

    sysroot: str | None = None
    gcc_toolchain: str | None = None
    apple_sdk_name: str | None = None
    apple_sysroot: str | None = None
    apple_min_version_flag: str | None = None
    # CRT/STL dirs before SDK dirs, mirroring vcvars ordering; passed as explicit
    # /imsvc + /libpath: flags because clang-cl and lld-link split INCLUDE/LIB on ';'
    # even on POSIX build machines.
    msvc_include_dirs: list[str] = field(default_factory=list)
    msvc_lib_dirs: list[str] = field(default_factory=list)

    extra_cflags: list[str] = field(default_factory=list)
    extra_cxxflags: list[str] = field(default_factory=list)
    extra_ldflags: list[str] = field(default_factory=list)
    extra_defines: list[str] = field(default_factory=list)
    stdlib: str | None = None

    msbuild_toolset: str | None = None
    msbuild_properties: dict[str, str] = field(default_factory=dict)

    cmake_toolchain_file: str | None = None

    def __bool__(self) -> bool:
        return any(getattr(self, f.name) not in (None, {}, []) for f in fields(self))

    def serialize(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def deserialize(content: dict[str, Any]) -> ToolchainInfo:
        known = {f.name for f in fields(ToolchainInfo)}
        return ToolchainInfo(**{k: v for k, v in content.items() if k in known})

    def merge(self, other: ToolchainInfo | None) -> None:
        if other is None:
            return
        for f in fields(self):
            current = getattr(self, f.name)
            if current in (None, {}, []):
                setattr(self, f.name, getattr(other, f.name))

    def set_relative_base_folder(self, folder: str) -> None:
        def _abs(value: str) -> str:
            return value if os.path.isabs(value) else os.path.join(folder, value)

        self.compilers = {lang: _abs(exe) for lang, exe in self.compilers.items()}
        for name in _PATH_FIELDS:
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, _abs(value))
        for name in _PATH_LIST_FIELDS:
            setattr(self, name, [_abs(v) for v in getattr(self, name)])


def find_toolchain(recipe: Any) -> ToolchainInfo | None:
    """The consumer's toolchain contract, looked up BY NAME (``settings.compiler_recipe``)
    in its dependency graph - ingredient recipes may publish contracts of their own for
    their provider role, so scanning for any contract would be ambiguous."""
    name = recipe.settings.compiler_recipe
    if not name:
        return None
    for view in (recipe.dependencies.host, recipe.dependencies.build):
        try:
            for require, dep in view.items():
                if str(require.name) == name and dep.info.toolchain:
                    return dep.info.toolchain
        except Exception:
            continue
    return None
