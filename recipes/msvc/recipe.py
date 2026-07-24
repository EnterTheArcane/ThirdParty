import re

import requests

from thirdparty import RecipeBase
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get, save
from thirdparty.microsoft import add_case_variant_symlinks
from thirdparty.scm import Version


# The MSVC CRT/STL ships with Visual Studio, not the Windows SDK, and has no NuGet, so the
# payloads come from the VS installer feed (as xwin/msvc-wine do); the channel manifest
# lists one .vsix (zip) per package, keyed by (guid, sha256) in its download URL.
# Headers = vcruntime + STL headers, <arch>.Desktop = static CRT libs, and <arch>.Store's
# top level = the *desktop* dynamic-CRT import libs (the actual store/uwp variants live in
# subfolders that package() excludes).
_ID_PREFIX = "Microsoft.VC.14.44.17.14"
_PAYLOADS = {
    "CRT.Headers": (
        "c610cd8c-801b-44b8-a80a-82cc382aeb43", "852382a9aa73502b7849c1bcadfb603ba7175c4e8b60e6aba03c7de711d4ece5"),
    "CRT.x64.Desktop": (
        "67cf767c-5e71-47c2-a54a-cd5631e28942", "f01f701a7bcd9587a340898c851424f6a52bb913a70c185ff0d5bf0288c5831a"),
    "CRT.x64.Store": (
        "67cf767c-5e71-47c2-a54a-cd5631e28942", "9135b03c0df53c7a0aa9bef7230a1c2ff4263a0ee7baa7e419d034f484f6bb56"),
    "CRT.ARM64.Desktop": (
        "67cf767c-5e71-47c2-a54a-cd5631e28942", "ba1aeca6d6470d2b3b318ec7bffb3e61f9a736cfb76d8a7d18e004a8e7c26651"),
    "CRT.ARM64.Store": (
        "67cf767c-5e71-47c2-a54a-cd5631e28942", "57ece91747be72fdd9ed0c39b83225011c8afba6b6f616a23ace54d0522f79e9"),
}

# Feed package-id arch fragment and on-disk lib folder for each recipe arch.
_ID_ARCH = {"X64": "x64", "ARM": "ARM64"}
_LIB_ARCH = {"X64": "x64", "ARM": "arm64"}

_CHANNEL_URL = "https://aka.ms/vs/17/release/channel"


class Recipe(RecipeBase):
    name = "msvc"
    # The toolset folder version inside the payloads (VC/Tools/MSVC/<version>), which the
    # feed's own package versions (14.44.352xx) don't quite match.
    version = "14.44.35207"
    license = "Microsoft Visual Studio License"

    def latest_version(self):
        channel = requests.get(_CHANNEL_URL, timeout=30)
        channel.raise_for_status()
        manifest_url = next(
            item["payloads"][0]["url"] for item in channel.json()["channelItems"]
            if item["id"] == "Microsoft.VisualStudio.Manifests.VisualStudio")
        manifest = requests.get(manifest_url, timeout=120)
        manifest.raise_for_status()
        series = {m.group(1) for m in re.finditer(r'"Microsoft\.VC\.(\d+\.\d+)\.', manifest.text)}
        # The full folder version only exists inside the payloads, so return the series:
        # 14.44 < 14.44.35207, meaning only a genuinely newer series reports as outdated.
        return Version(max(series, key=Version))

    def validate(self):
        if str(self.settings.os) != "Windows":
            raise RecipeInvalidConfiguration(f"{self.name} only provides Windows CRT/STL libraries")

    def build(self):
        arch = _ID_ARCH[str(self.settings.arch)]
        for kind in ("CRT.Headers", f"CRT.{arch}.Desktop", f"CRT.{arch}.Store"):
            guid, sha256 = _PAYLOADS[kind]
            filename = f"{_ID_PREFIX}.{kind}.base.vsix"
            get(
                self,
                url=f"https://download.visualstudio.microsoft.com/download/pr/{guid}/{sha256}/{filename}",
                sha256=sha256,
                destination=self.folders.build,
                filename=filename)

    def package(self):
        root = self.folders.build / "Contents" / "VC" / "Tools" / "MSVC" / self.version
        pkg = self.folders.package
        lib_arch = _LIB_ARCH[str(self.settings.arch)]

        copy(self, "*", src=root / "include", dst=pkg / "include")
        copy(self, "*", src=root / "modules", dst=pkg / "modules")
        # Only the top-level desktop libs; the store/uwp/enclave variants are not needed.
        copy(
            self, "*", src=root / "lib" / lib_arch, dst=pkg / "lib" / lib_arch, excludes=("store/*", "uwp/*", "enclave/*", "onecore/*"))

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
