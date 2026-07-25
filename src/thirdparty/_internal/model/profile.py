from __future__ import annotations

from dataclasses import dataclass, replace

from thirdparty._internal.util import detect


@dataclass(frozen=True)
class BuildProfile:
    """What a build invocation targets: build type, target platform, and toolchain.

    One immutable value threaded from the CLI through graph resolution and recipe
    instantiation, replacing loose (build_type, target_os, target_arch) parameter
    triples. ``compiler`` is the requested toolchain provider recipe name (e.g.
    "clang"); None means auto-select (see ``_internal/toolchains.py``).
    """

    build_type: str = "Release"
    target_os: str | None = None
    target_arch: str | None = None
    compiler: str | None = None

    @property
    def is_cross(self) -> bool:
        return self.target_os is not None or self.target_arch is not None

    def build_machine(self) -> "BuildProfile":
        """This profile pointed at the build machine (tool-dependency context).

        The compiler choice is kept: a hermetic toolchain applies to build-machine
        tools exactly as it does to target packages.
        """
        return replace(self, target_os=None, target_arch=None)

    def with_target(self, target_os: str | None, target_arch: str | None) -> "BuildProfile":
        return replace(self, target_os=target_os, target_arch=target_arch)

    def to_settings(self):
        """Base target settings (os/arch/build_type/apple sdk), WITHOUT compiler fields.

        Compiler fields are filled by toolchain selection - use
        ``thirdparty._internal.toolchains.resolve_settings`` for complete settings.
        """
        return detect.detect_settings(self.build_type, self.target_os, self.target_arch)
