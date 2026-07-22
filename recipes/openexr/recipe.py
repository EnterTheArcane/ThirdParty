import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, rmdir, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "openexr"
    version = "3.4.13"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "AcademySoftwareFoundation/openexr")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("zlib")
        self.requires("imath")
        self.requires("libdeflate")

        self.requires("openjph")

    def source(self):
        get(
            self,
            url=f"https://github.com/AcademySoftwareFoundation/openexr/releases/download/v{self.version}/openexr-{self.version}.tar.gz",
            sha256="fe99c9cf06e41803db75ae4f5c9bb9955b7033ff47f05b02bc60bc5dba391996",
            destination=self.folders.source,
            strip_root=True)
        replace_in_file(
            self,
            self.folders.source / "CMakeLists.txt",
            "add_subdirectory(website/src)",
            "# add_subdirectory(website/src)")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["OPENEXR_INSTALL_EXAMPLES"] = False
        tc.variables["BUILD_TESTING"] = False
        tc.variables["BUILD_WEBSITE"] = False
        tc.variables["DOCS"] = False
        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("openjph", "cmake_target_name", "openjph")
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.md", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "OpenEXR")
        self.info.set_property("pkg_config_name", "OpenEXR")

        lib_suffix = ""
        if not self.options.shared or self.settings.os == "Windows":
            openexr_version = Version(self.version)
            lib_suffix += f"-{openexr_version.major}_{openexr_version.minor}"
        if self.settings.build_type == "Debug":
            lib_suffix += "_d"

        # OpenEXR::OpenEXRConfig
        OpenEXRConfig = self._add_component("OpenEXRConfig")
        OpenEXRConfig.includedirs.append(os.path.join("include", "OpenEXR"))

        # OpenEXR::IexConfig
        IexConfig = self._add_component("IexConfig")
        IexConfig.includedirs = OpenEXRConfig.includedirs

        # OpenEXR::IlmThreadConfig
        IlmThreadConfig = self._add_component("IlmThreadConfig")
        IlmThreadConfig.includedirs = OpenEXRConfig.includedirs

        # OpenEXR::Iex
        Iex = self._add_component("Iex")
        Iex.libs = [f"Iex{lib_suffix}"]
        Iex.requires = [_recipe_comp("IexConfig")]
        if self.settings.os in ["Linux", "FreeBSD"]:
            Iex.system_libs = ["m"]

        # OpenEXR::IlmThread
        IlmThread = self._add_component("IlmThread")
        IlmThread.libs = [f"IlmThread{lib_suffix}"]
        IlmThread.requires = [
            _recipe_comp("IlmThreadConfig"), _recipe_comp("Iex"),
        ]
        if self.settings.os in ["Linux", "FreeBSD"]:
            IlmThread.system_libs = ["pthread", "m"]

        # OpenEXR::OpenEXRCore
        OpenEXRCore = self._add_component("OpenEXRCore")
        OpenEXRCore.libs = [f"OpenEXRCore{lib_suffix}"]
        OpenEXRCore.requires = [_recipe_comp("OpenEXRConfig"), "zlib::zlib"]
        OpenEXRCore.requires.append("libdeflate::libdeflate")
        OpenEXRCore.requires.append("openjph::openjph")
        if self.settings.os in ["Linux", "FreeBSD"]:
            OpenEXRCore.system_libs = ["m"]

        # OpenEXR::OpenEXR
        OpenEXR = self._add_component("OpenEXR")
        OpenEXR.libs = [f"OpenEXR{lib_suffix}"]
        OpenEXR.requires = [
            _recipe_comp("OpenEXRCore"), _recipe_comp("IlmThread"),
            _recipe_comp("Iex"), "imath::imath",
        ]
        if self.settings.os in ["Linux", "FreeBSD"]:
            OpenEXR.system_libs = ["m"]

        # OpenEXR::OpenEXRUtil
        OpenEXRUtil = self._add_component("OpenEXRUtil")
        OpenEXRUtil.libs = [f"OpenEXRUtil{lib_suffix}"]
        OpenEXRUtil.requires = [_recipe_comp("OpenEXR")]
        if self.settings.os in ["Linux", "FreeBSD"]:
            OpenEXRUtil.system_libs = ["m"]

        # TODO: Add tools directory to PATH

    def _add_component(self, name: str):
        component = self.info.components[_recipe_comp(name)]
        component.set_property("cmake_target_name", f"OpenEXR::{name}")
        return component

@staticmethod
def _recipe_comp(name: str):
    return f"openexr_{name.lower()}"
