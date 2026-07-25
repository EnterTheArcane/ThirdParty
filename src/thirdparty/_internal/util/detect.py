from __future__ import annotations
import platform

from thirdparty._internal.model.settings import Settings


# Canonical platform names used by this system (deliberately simpler than Conan's full set).
_OS_NAMES = ("Windows", "Linux", "Mac", "Android", "iOS", "tvOS", "visionOS")
_ARCH_NAMES = ("X64", "ARM")
_APPLE_DEVICE_OSES = {"iOS", "tvOS", "visionOS"}
_APPLE_SDK_DEFAULTS = {
    ("iOS", "ARM"): "iphoneos",
    ("iOS", "X64"): "iphonesimulator",
    ("tvOS", "ARM"): "appletvos",
    ("tvOS", "X64"): "appletvsimulator",
    ("visionOS", "ARM"): "xros",
    ("visionOS", "X64"): "xrsimulator",
}


def normalize_os(name: str | None) -> str | None:
    """Case-insensitively match *name* to a canonical OS name (e.g. ``mac`` -> ``Mac``).

    Unknown names are returned unchanged (settings validation handles the rest).
    """
    if name is None:
        return None
    for canon in _OS_NAMES:
        if name.strip().lower() == canon.lower():
            return canon
    return name


def normalize_arch(name: str | None) -> str | None:
    """Case-insensitively match *name* to a canonical arch name (e.g. ``arm`` -> ``ARM``)."""
    if name is None:
        return None
    for canon in _ARCH_NAMES:
        if name.strip().lower() == canon.lower():
            return canon
    return name


def _machine_os() -> str:
    the_os = platform.system()
    return "Mac" if the_os == "Darwin" else the_os


def _machine_arch() -> str:
    machine = platform.machine().lower()
    return "ARM" if ("arm64" in machine or "aarch64" in machine) else "X64"


def _default_target_arch(the_os: str, target_arch: str | None) -> str:
    arch = normalize_arch(target_arch)
    if arch:
        return arch
    if the_os in _APPLE_DEVICE_OSES:
        return "ARM"
    return _machine_arch()


def detect_settings(build_type: str = "Release", target_os: str | None = None, target_arch: str | None = None) -> Settings:
    """Base settings for the *target* platform: os, arch, build type, Apple SDK default.

    ``target_os``/``target_arch`` select the HOST/target platform the package will run
    on (defaulting to the build machine).  Compiler fields are deliberately NOT set
    here: toolchains come from recipes, selected by
    ``thirdparty._internal.toolchains`` (which fills ``compiler``/``compiler_recipe``
    and friends via ``apply_compiler_settings``) - never probed from ambient machine
    state.
    """
    machine_os = _machine_os()
    the_os = normalize_os(target_os) or machine_os
    arch = _default_target_arch(the_os, target_arch)

    settings = Settings(os=the_os, arch=arch, build_type=build_type)

    apple_sdk = _APPLE_SDK_DEFAULTS.get((the_os, arch))
    if apple_sdk:
        settings.os_sdk = apple_sdk

    # os.version (deployment target) applies to the TARGET os; only known when the build
    # machine is itself a Mac.
    if the_os == "Mac" and machine_os == "Mac":
        _raw_ver = platform.mac_ver()[0]
        if _raw_ver:
            _parts = _raw_ver.split(".")
            _os_version = ".".join(_parts[:2]) if len(_parts) >= 2 else _parts[0]
            settings.os_version = _os_version

    return settings


def platform_tag(settings: Settings) -> str:
    """Return the output-folder platform tag for *settings*, e.g. ``windows-x64``.

    Build outputs are grouped by OS and architecture so that packages built for
    different platforms never share an output folder.  The tag is derived from the
    *host* settings (the platform the package will run on) - which is what governs
    binary compatibility - NOT the build machine.

    NOTE on HOST vs BUILD context: tools that run during the build (``requires_tool``
    such as cmake/ninja/nasm) must be built/located for the *build machine* and so
    should use the build-machine tag, while regular library dependencies use the
    host/target tag.  Today host == build == the detected machine, so a single tag
    is correct; when cross-compilation is introduced this distinction matters.
    """
    os_name = str(getattr(settings, "os", None) or "unknown").lower()
    arch = str(getattr(settings, "arch", None) or "unknown").lower()
    return f"{os_name}-{arch}"


def detect_platform_tag(target_os: str | None = None, target_arch: str | None = None) -> str:
    """Lightweight platform tag for a target (no compiler probing).

    Defaults to the current machine.  Produces the same string as :func:`platform_tag`
    applied to :func:`detect_settings` with the same overrides, but without shelling out
    to detect the compiler - cheap enough to call for status display and folder paths.
    """
    the_os = normalize_os(target_os) or _machine_os()
    arch = _default_target_arch(the_os, target_arch)
    return f"{the_os}-{arch}".lower()

