import json
import re
from pathlib import Path

import requests

from thirdparty import RecipeBase
from thirdparty._internal.model.settings import Settings
from thirdparty.errors import RecipeException, RecipeInvalidConfiguration
from thirdparty.files import copy, get, save
from thirdparty.microsoft import add_case_variant_symlinks
from thirdparty.scm import Version


# The MSVC toolset ships with Visual Studio, not the Windows SDK, so the compiler, linker,
# CRT and STL come from the VS installer feed (as xwin/msvc-wine do). The channel manifest
# lists every component as a .vsix keyed by id; the ".base" package of an id carries the
# payload and its ".Res.base" en-US sibling carries the localized resource DLLs (clui.dll
# et al. under 1033/) without which cl.exe aborts with C1510. Package ids drift in casing
# (Tools.HostX64.TargetX64 vs Tools.HostARM64.Targetx64), so payloads are resolved from the
# live manifest by case-insensitive id rather than pinned by hash. Both HostX64 and
# HostARM64 tool flavors are packaged so the package id stays the target <os>-<arch> alone.
_SERIES = "14.44.17.14"
_ID_PREFIX = f"Microsoft.VC.{_SERIES}"
_CHANNEL_URL = "https://aka.ms/vs/17/release/channel"

# Feed id fragment and on-disk lib/bin folder for each recipe arch.
_FEED_ARCH = {"X64": "X64", "ARM": "ARM64"}
_LIB_ARCH = {"X64": "x64", "ARM": "arm64"}
_HOST_DIR = {"X64": "Hostx64", "ARM": "Hostarm64"}


class Recipe(RecipeBase):
    name = "msvc"
    # The toolset folder version inside the payloads (VC/Tools/MSVC/<version>), which the
    # feed's own component versions (14.44.352xx) don't quite match. package() asserts the
    # payloads still ship this exact folder so the published VCToolsVersion stays correct.
    version = "14.44.35207"
    license = "Microsoft Visual Studio License"

    def latest_version(self):
        series: set[str] = set()
        for pkg in _load_manifest(self)["packages"]:
            m = re.match(r"Microsoft\.VC\.(\d+\.\d+)\.", str(pkg["id"]))
            if m:
                series.add(m.group(1))
        # The full folder version only exists inside the payloads, so compare on the series:
        # 14.44 < 14.44.35207, meaning only a genuinely newer series reports as outdated.
        return Version(max(series, key=Version))

    def validate(self):
        if str(self.settings.os) != "Windows":
            raise RecipeInvalidConfiguration(f"{self.name} only provides the Windows CRT/STL/toolset")
        # As the selected toolchain the packaged cl.exe must run on the build machine; as a
        # CRT/STL ingredient of the clang toolchain (compiler_recipe != "msvc") any build
        # machine is fine, e.g. cross-targeting Windows from Linux.
        if self.settings.compiler_recipe == self.name and str(self.settings_build.os) != "Windows":
            raise RecipeInvalidConfiguration(
                "the msvc toolchain (cl.exe) only runs on Windows build machines; "
                "use the clang toolchain to cross-target Windows")

    def toolchain_settings(self, settings: Settings):
        settings.compiler = "msvc"
        settings.compiler_runtime = "dynamic"

    def requirements(self):
        self.requires("windows-sdk")

    def build(self):
        arch = _FEED_ARCH[str(self.settings.arch)]
        packages = _index(_load_manifest(self))
        neutral = (
            f"{_ID_PREFIX}.CRT.Headers.base",
            f"{_ID_PREFIX}.CRT.{arch}.Desktop.base",
            f"{_ID_PREFIX}.CRT.{arch}.Store.base",
            f"{_ID_PREFIX}.Tools.HostX64.Target{arch}.base",
            f"{_ID_PREFIX}.Tools.HostARM64.Target{arch}.base",
        )
        localized = (
            f"{_ID_PREFIX}.Tools.HostX64.Target{arch}.Res.base",
            f"{_ID_PREFIX}.Tools.HostARM64.Target{arch}.Res.base",
        )
        for pid in neutral:
            _fetch(self, _select(packages, pid, None))
        for pid in localized:
            _fetch(self, _select(packages, pid, "en-US"))

    def package(self):
        msvc_root = self.folders.build / "Contents" / "VC" / "Tools" / "MSVC"
        shipped = sorted(p.name for p in msvc_root.iterdir()) if msvc_root.is_dir() else []
        if self.version not in shipped:
            raise RecipeException(
                f"the VS feed no longer ships MSVC toolset {self.version} (found: {shipped or 'none'}); "
                f"update the version pin in the {self.name} recipe")
        root = msvc_root / self.version
        pkg = self.folders.package
        lib_arch = _LIB_ARCH[str(self.settings.arch)]

        copy(self, "*", src=root / "include", dst=pkg / "include")
        copy(self, "*", src=root / "modules", dst=pkg / "modules")
        # Only the top-level desktop libs; the store/uwp/enclave variants are not needed.
        copy(
            self, "*", src=root / "lib" / lib_arch, dst=pkg / "lib" / lib_arch, excludes=("store/*", "uwp/*", "enclave/*", "onecore/*"))
        # Compiler/linker binaries for the target arch, both host flavors (each carries its
        # own 1033/ resource DLLs from the .Res.base payloads).
        for host_dir in _HOST_DIR.values():
            src = root / "bin" / host_dir / lib_arch
            if src.is_dir():
                copy(self, "*", src=src, dst=pkg / "bin" / host_dir / lib_arch)

        # The toolset license is part of the Visual Studio license (URL-only), record it.
        save(
            self,
            pkg / "licenses" / "NOTICE.txt",
            f"Microsoft Visual C++ Build Tools ({self.version})\n"
            "(c) Microsoft Corporation. All rights reserved.\n"
            "Licensed under the Microsoft Visual Studio License Terms.\n"
            "https://visualstudio.microsoft.com/license-terms/\n")

        add_case_variant_symlinks(
            self, include_dirs=[pkg / "include"], lib_dirs=[pkg / "lib" / lib_arch])

    def package_info(self):
        self.info.redistributable = False
        root = self.folders.package
        lib_arch = _LIB_ARCH[str(self.settings.arch)]

        self.info.includedirs = ["include"]
        self.info.libdirs = [f"lib/{lib_arch}"]

        self.info.set_property("cmake_file_name", "MSVCRuntime")
        self.info.set_property("cmake_target_name", "MSVCRuntime::MSVCRuntime")

        self.info.buildenv.define_path("VCToolsInstallDir", root)
        self.info.buildenv.define("VCToolsVersion", self.version)
        for d in self.info.includedirs:
            self.info.buildenv.append_path("INCLUDE", root / d)
        for d in self.info.libdirs:
            self.info.buildenv.append_path("LIB", root / d)

        bin_dir = root / "bin" / _HOST_DIR[str(self.settings_build.arch)] / lib_arch
        if not (bin_dir / "cl.exe").exists():
            return
        self.info.toolchain.family = "msvc"
        self.info.toolchain.front_kind = "msvc"
        self.info.toolchain.compilers = {"c": str(bin_dir / "cl.exe"), "cpp": str(bin_dir / "cl.exe")}
        self.info.toolchain.linker = str(bin_dir / "link.exe")
        self.info.toolchain.ar = str(bin_dir / "lib.exe")
        self.info.toolchain.lib = str(bin_dir / "lib.exe")
        asm = bin_dir / ("ml64.exe" if lib_arch == "x64" else "armasm64.exe")
        if asm.exists():
            self.info.toolchain.compilers["asm"] = str(asm)
        sdk = self.dependencies["windows-sdk"]
        rc, mt = _find_sdk_tools(sdk, _HOST_DIR[str(self.settings_build.arch)].removeprefix("Host"))
        if rc:
            self.info.toolchain.compilers["rc"] = rc
        if mt:
            self.info.toolchain.mt = mt
        self.info.toolchain.msvc_include_dirs = [str(root / d) for d in self.info.includedirs]
        self.info.toolchain.msvc_lib_dirs = [str(root / d) for d in self.info.libdirs]
        self.info.toolchain.msvc_include_dirs += [str(d) for d in sdk.info.includedirs]
        self.info.toolchain.msvc_lib_dirs += [str(d) for d in sdk.info.libdirs]
        self.info.toolchain.msbuild_toolset = "v143"
        self.info.toolchain.msbuild_properties = {"VCToolsVersion": self.version}


def _load_manifest(recipe: RecipeBase) -> dict:
    channel = requests.get(_CHANNEL_URL, timeout=60)
    channel.raise_for_status()
    manifest_url = next(
        item["payloads"][0]["url"] for item in channel.json()["channelItems"]
        if item["id"] == "Microsoft.VisualStudio.Manifests.VisualStudio")
    manifest = requests.get(manifest_url, timeout=300)
    manifest.raise_for_status()
    return json.loads(manifest.text)


def _index(manifest: dict) -> dict[str, list[dict]]:
    by_id: dict[str, list[dict]] = {}
    for pkg in manifest["packages"]:
        by_id.setdefault(str(pkg["id"]).lower(), []).append(pkg)
    return by_id


def _select(packages: dict[str, list[dict]], pid: str, language: str | None) -> dict:
    for pkg in packages.get(pid.lower(), ()):
        if str(pkg.get("type")) != "Vsix":
            continue
        lang = str(pkg.get("language", "") or "")
        if (language is None and lang in ("", "neutral")) or lang == language:
            return pkg
    raise RecipeException(
        f"VS manifest has no {language or 'neutral'} '{pid}' package; "
        f"update the id table in the msvc recipe")


def _fetch(recipe: RecipeBase, pkg: dict):
    for payload in pkg["payloads"]:  # one vsix per package in practice
        filename = re.sub(r"[^A-Za-z0-9._-]", "_", str(payload["fileName"]))
        get(
            recipe, url=payload["url"], sha256=str(payload["sha256"]).lower(),
            destination=recipe.folders.build, filename=filename)


def _find_sdk_tools(sdk: RecipeBase, host_arch_dir: str) -> "tuple[str | None, str | None]":
    """Locate rc.exe / mt.exe inside the windows-sdk package (bin/<ver>/<arch>/).

    The tools RUN on the build machine, so the host arch dir is preferred.
    """
    rc = mt = None
    want = host_arch_dir.lower()
    for bindir in sdk.info.bindirs:
        base = Path(bindir)
        if not base.is_dir():
            continue
        for candidate in sorted(base.rglob("rc.exe")):
            if candidate.parent.name.lower() == want:
                rc = rc or str(candidate)
        for candidate in sorted(base.rglob("mt.exe")):
            if candidate.parent.name.lower() == want:
                mt = mt or str(candidate)
        if rc and mt:
            break
    return rc, mt
