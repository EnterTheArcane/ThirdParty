from thirdparty import RecipeBase
from thirdparty.files import copy, get, save
from thirdparty.microsoft import add_case_variant_symlinks
from thirdparty.scm import NugetPackage, Version


# Keyed by NuGet package id. The flat-container API lowercases ids in the URL, so ids must be
# lowercase here (they double as the download filename). Both arch lib packages are listed, but a
# build only pulls the one matching the target arch.
_SHA256 = {
    "microsoft.windows.sdk.buildtools": "a09a4c9d68160ced4765137a9a7444ea560ea86c45d6a77093dea58c2f7563a0",
    "microsoft.windows.sdk.cpp.arm64": "f890c85f46cc76c094f30fa555a438a212ee3d36165bcd7afdca96bb52c9bc7a",
    "microsoft.windows.sdk.cpp.x64": "a9cae2a8c5da7f5dc5838ae6a76d06d0d2e2fdc3d8cfc69ca6c184e4b9193a00",
    "microsoft.windows.sdk.cpp": "be1b419491607eae6f7c57844ebab39face9643c51e2af1d9176a3ba0d0b23fc",
}

_ARCH = {"X64": "x64", "ARM": "arm64"}
_INCLUDE_SUBDIRS = ("ucrt", "shared", "um", "winrt", "cppwinrt")
_LIB_APIS = ("ucrt", "um")


class Recipe(RecipeBase):
    name = "windows-sdk"
    version = "10.0.28000.2526"
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

        add_case_variant_symlinks(
            self,
            include_dirs=[pkg / "include" / s for s in _INCLUDE_SUBDIRS],
            lib_dirs=[pkg / "lib" / api / arch for api in _LIB_APIS])

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
