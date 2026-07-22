import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "imath"
    version = "3.2.2"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "AcademySoftwareFoundation/Imath")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/AcademySoftwareFoundation/Imath/releases/download/v{self.version}/Imath-{self.version}.tar.gz",
            sha256="0f5a783b424f374e6f27ec8b0c73130e89b08814ac8fa2e84fd7fe0b05862c53",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["BUILD_TESTING"] = False
        if is_msvc(self) and self.settings.compiler_cxx_standard:
            # when msvc is working with a C++ standard level higher
            # than the default, we need the __cplusplus macro to be correct
            tc.variables["CMAKE_CXX_FLAGS"] = "/Zc:__cplusplus"
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.md", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "Imath")
        self.info.set_property("cmake_target_name", "Imath::Imath")
        self.info.set_property("pkg_config_name", "Imath")

        # Imath::ImathConfig - header only library
        imath_config = self.info.components["imath_config"]
        imath_config.set_property("cmake_target_name", "Imath::ImathConfig")
        imath_config.includedirs.append(os.path.join("include", "Imath"))

        # Imath::Imath - linkable library
        suffix = f"-{Version(self.version).major}_{Version(self.version).minor}"
        if self.settings.build_type == "Debug":
            suffix += "_d"
        imath_lib = self.info.components["imath_lib"]
        imath_lib.set_property("cmake_target_name", "Imath::Imath")
        imath_lib.set_property("pkg_config_name", "Imath")
        imath_lib.libs = [f"Imath{suffix}"]
        imath_lib.requires = ["imath_config"]
        if self.settings.os == "Windows" and self.options.shared:
            imath_lib.defines.append("IMATH_DLL")
        elif self.settings.os in ["Linux", "FreeBSD"]:
            imath_lib.system_libs.append("m")
