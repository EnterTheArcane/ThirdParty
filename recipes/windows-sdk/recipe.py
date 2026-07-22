from thirdparty import RecipeBase
from thirdparty.files import copy, get, save
from thirdparty.scm import NugetPackage, Version


# Keyed by NuGet package id. The flat-container API lowercases ids in the URL, so ids must be
# lowercase here (they double as the download filename). Both arch lib packages are listed, but a
# build only pulls the one matching the target arch.
_SHA256 = {
    "microsoft.windows.sdk.buildtools": "d939fa052f9c80f878b2a28b7071a6f2c9a51029018bb87a835ebda6e535a002",
    "microsoft.windows.sdk.cpp.arm64": "543c2b31dfa77e00cc63860a587178c5c90837f64c05b05f73cb18b1c33f549a",
    "microsoft.windows.sdk.cpp.x64": "72076d00b16c3882bf9eab0c80e350f33d8bc65e5f29e2f0e9b66a3f2569ccb1",
    "microsoft.windows.sdk.cpp": "0a4887a64d1b17128f9ffd80032f20debabf943f34eea927aac00cc46cb32879",
}

_ARCH = {"X64": "x64", "ARM": "arm64"}
_INCLUDE_SUBDIRS = ("ucrt", "shared", "um", "winrt", "cppwinrt")
_LIB_APIS = ("ucrt", "um")


class Recipe(RecipeBase):
    name = "windows-sdk"
    version = "10.0.28000.2270"
    sdk_version = "10.0.28000.0"
    nuget_version = version
    license = "Microsoft Windows SDK License"

    def latest_version(self):
        package = NugetPackage(self, "microsoft.windows.sdk.cpp")
        return Version(package.latest_release)

    def build(self) -> None:
        # Headers/sources, the target-arch libs only, and the tools -- not both arches.
        cpp_arch = f"microsoft.windows.sdk.cpp.{_ARCH[self.settings.arch]}"
        for pkg_id in ("microsoft.windows.sdk.cpp", cpp_arch, "microsoft.windows.sdk.buildtools"):
            filename = f"{pkg_id}.{self.nuget_version}.nupkg"
            get(
                self,
                url=f"https://api.nuget.org/v3-flatcontainer/{pkg_id}/{self.nuget_version}/{filename}",
                sha256=_SHA256[pkg_id],
                destination=self.folders.build,
                filename=filename)

    def package(self) -> None:
        build = self.folders.build
        pkg = self.folders.package
        arch = _ARCH[self.settings.arch]
        host = _ARCH[self.settings_build.arch]

        copy(self, "*", src=build / "c" / "Include" / self.sdk_version, dst=pkg / "include")
        copy(self, "*", src=build / "c" / "Source" / self.sdk_version, dst=pkg / "src")
        for api in _LIB_APIS:
            copy(self, "*", src=build / "c" / api / arch, dst=pkg / "lib" / api / arch)
        copy(self, "*", src=build / "bin" / self.sdk_version / host, dst=pkg / "bin")

        # The SDK license is URL-only (nuspec licenseUrl), record it.
        # cppwinrt ships its own LICENSE.txt alongside its headers under include/cppwinrt.
        save(
            self,
            self.folders.package / "licenses" / "NOTICE.txt",
            f"Microsoft Windows SDK ({self.sdk_version})\n"
            "(c) Microsoft Corporation. All rights reserved.\n"
            "Licensed under the Microsoft Software License Terms for the Windows SDK.\n"
            "https://aka.ms/WinSDKLicenseURL\n")

    def package_info(self) -> None:
        root = self.folders.package
        arch = _ARCH[self.settings.arch]

        self.info.includedirs = [f"include/{s}" for s in _INCLUDE_SUBDIRS]
        self.info.libdirs = [f"lib/{api}/{arch}" for api in _LIB_APIS]
        self.info.bindirs = ["bin"]

        self.info.set_property("cmake_file_name", "WindowsSDK")
        self.info.set_property("cmake_target_name", "WindowsSDK::WindowsSDK")

        self.info.buildenv.define_path("WindowsSdkDir", root)
        self.info.buildenv.define("WindowsSDKVersion", f"{self.sdk_version}\\")
        self.info.buildenv.define("UCRTVersion", self.sdk_version)
        for d in self.info.includedirs:
            self.info.buildenv.append_path("INCLUDE", root / d)
        for d in self.info.libdirs:
            self.info.buildenv.append_path("LIB", root / d)
        self.info.buildenv.prepend_path("PATH", root / "bin")
