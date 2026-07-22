from __future__ import annotations
import os
import platform
import re
import subprocess
from functools import lru_cache

from thirdparty._internal.model.settings import Settings


@lru_cache(maxsize=1)
def _detect_msvc_version():
    vswhere = os.path.join(
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Microsoft Visual Studio", "Installer", "vswhere.exe", )
    if not os.path.exists(vswhere):
        return None
    try:
        install_path = subprocess.check_output(
            [
                vswhere, "-latest", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath",
            ], text=True, stderr=subprocess.DEVNULL, ).strip()
        if not install_path:
            return None
        ver_file = os.path.join(
            install_path, "VC", "Auxiliary", "Build", "Microsoft.VCToolsVersion.default.txt", )
        if not os.path.exists(ver_file):
            return None
        with open(ver_file) as f:
            full_ver = f.read().strip()
        parts = full_ver.split(".")
        minor = int(parts[1])
        # VCTools 14.Nx.x -> recipe msvc "19N" (14.3x=193, 14.4x=194, ...)
        return str(190 + minor // 10)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _detect_apple_clang_version() -> str | None:
    for cmd in (["xcrun", "clang", "--version"], ["clang", "--version"]):
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
            m = re.search(r"Apple clang version (\d+)", out, re.IGNORECASE)
            if m:
                return m.group(1)
        except Exception:
            continue
    return None


@lru_cache(maxsize=1)
def _detect_linux_compiler():
    for exe in ("gcc", "clang", "cc", "x86_64-linux-gnu-gcc", "aarch64-linux-gnu-gcc"):
        try:
            out = subprocess.check_output(
                [exe, "--version"], text=True, stderr=subprocess.STDOUT, )
            if "clang" in out.lower():
                m = re.search(r"clang version (\d+)", out)
                if m:
                    return "clang", m.group(1)
            else:
                m = re.search(r"(\d+)\.\d+", out.splitlines()[0])
                if m:
                    return "gcc", m.group(1)
        except Exception:
            continue
    return None, None


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
    """Detect build settings for the *target* platform.

    ``target_os``/``target_arch`` select the HOST/target platform the package will run
    on (defaulting to the build machine).  The compiler, however, is always detected from
    the BUILD MACHINE - it is the toolchain that exists locally and does the compiling.
    For same-OS cross-architecture builds (e.g. X64 -> ARM) this is exactly right;
    the target arch flows into the toolchain via ``settings.arch`` (and, for MSVC + Ninja,
    into the vcvars argument computed from ``settings_build.arch`` vs ``settings.arch``).
    """
    machine_os = _machine_os()
    the_os = normalize_os(target_os) or machine_os
    arch = _default_target_arch(the_os, target_arch)

    settings = Settings(os=the_os, arch=arch, build_type=build_type)

    apple_sdk = _APPLE_SDK_DEFAULTS.get((the_os, arch))
    if apple_sdk:
        settings.os_sdk = apple_sdk

    # Compiler detection is keyed on the BUILD MACHINE os (the locally available toolchain).
    if machine_os == "Windows":
        msvc_ver = _detect_msvc_version()
        if msvc_ver:
            settings.compiler = "msvc"
            settings.compiler_version = msvc_ver
            settings.compiler_runtime = "dynamic"
            settings.compiler_cxx_standard = "17"
    elif machine_os == "Mac":
        ver = _detect_apple_clang_version()
        if ver:
            settings.compiler = "apple-clang"
            settings.compiler_version = ver + ".0"
            settings.compiler_libcxx = "libc++"
            settings.compiler_cxx_standard = "17"
    else:
        compiler, ver = _detect_linux_compiler()
        if compiler == "gcc":
            settings.compiler = "gcc"
            settings.compiler_version = ver
            settings.compiler_libcxx = "libstdc++11"
            settings.compiler_cxx_standard = "17"
        elif compiler == "clang":
            settings.compiler = "clang"
            settings.compiler_version = ver
            settings.compiler_libcxx = "libc++"
            settings.compiler_cxx_standard = "17"

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

