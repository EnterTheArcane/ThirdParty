import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "opus"
    version = "1.6.1"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "xiph/opus")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/xiph/opus/archive/refs/tags/v{self.version}.tar.gz",
            sha256="bf0b97ec7a65890b8db90ef94c4d6c18de12584c3085031953a10986f5917745",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["OPUS_BUILD_SHARED_LIBRARY"] = self.options.shared
        tc.cache_variables["OPUS_FIXED_POINT"] = False
        tc.cache_variables["OPUS_STACK_PROTECTOR"] = True
        if is_msvc(self):
            tc.cache_variables["OPUS_STATIC_RUNTIME"] = is_msvc_static_runtime(self)
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "Opus")
        self.info.set_property("cmake_target_name", "Opus::opus")
        self.info.set_property("pkg_config_name", "opus")
        self.info.components["libopus"].libs = ["opus"]
        self.info.components["libopus"].includedirs.append(os.path.join("include", "opus"))
        if self.settings.os in ["Linux", "FreeBSD", "Android"]:
            self.info.components["libopus"].system_libs.append("m")
        if self.settings.os == "Windows" and self.settings.compiler == "gcc":
            self.info.components["libopus"].system_libs.append("ssp")

        self.info.components["libopus"].set_property("cmake_target_name", "Opus::opus")
        self.info.components["libopus"].set_property("pkg_config_name", "opus")
